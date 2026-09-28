#!/usr/bin/env python3
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("release_check", ROOT / "scripts/release-check.py")
assert spec is not None and spec.loader is not None
release_check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release_check)


def archive(commit: str, version: str, name: str = "parabol-action") -> bytes:
    output = io.BytesIO()
    data = json.dumps({"name": name, "version": version}).encode()
    with tarfile.open(fileobj=output, mode="w:gz") as bundle:
        info = tarfile.TarInfo(f"parabol-{commit}/package.json")
        info.size = len(data)
        bundle.addfile(info, io.BytesIO(data))
    return output.getvalue()


class ReleaseCheckTests(unittest.TestCase):
    def test_ignores_drafts_prereleases_and_non_semver_tags(self):
        releases = [
            {"tag_name": "v99.0.0", "prerelease": True, "draft": False},
            {"tag_name": "v98.0.0", "prerelease": False, "draft": True},
            {"tag_name": "nightly", "prerelease": False, "draft": False},
            {"tag_name": "v14.2.0", "prerelease": False, "draft": False},
            {"tag_name": "v14.10.0", "prerelease": False, "draft": False},
        ]
        self.assertEqual(release_check.stable_release(releases)["tag_name"], "v14.10.0")

    def test_no_stable_release_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "no stable"):
            release_check.stable_release(
                [{"tag_name": "v15.0.0-rc.1", "draft": False, "prerelease": True}]
            )

    def test_discover_validates_tag_commit_version_and_checksum(self):
        commit = "a" * 40
        payload = archive(commit, "15.0.0")
        calls = []

        def get_json(url):
            calls.append(url)
            if "releases?" in url:
                return [{"tag_name": "v15.0.0", "prerelease": False, "draft": False}]
            return {"object": {"type": "commit", "sha": commit}}

        pin = release_check.discover(get_json=get_json, fetch=lambda _: payload)
        self.assertEqual(pin["commit"], commit)
        self.assertEqual(pin["archive_sha256"], hashlib.sha256(payload).hexdigest())
        self.assertTrue(any("git/ref/tags/v15.0.0" in call for call in calls))

    def test_annotated_tag_is_peeled_to_commit(self):
        tag_object = "b" * 40
        commit = "c" * 40

        def get_json(url):
            if "/git/ref/tags/" in url:
                return {"object": {"type": "tag", "sha": tag_object}}
            return {"object": {"type": "commit", "sha": commit}}

        self.assertEqual(release_check.peel_commit("v15.0.0", get_json), commit)

    def test_archive_rejects_tag_package_mismatch_and_wrong_root(self):
        commit = "d" * 40
        with self.assertRaisesRegex(ValueError, "disagree"):
            release_check.validate_archive("v15.0.0", commit, archive(commit, "14.0.1"))
        payload = archive("e" * 40, "15.0.0")
        with self.assertRaisesRegex(ValueError, "expected commit root"):
            release_check.validate_archive("v15.0.0", commit, payload)

    def test_evaluate_is_side_effect_free_and_reports_payload(self):
        current = {"tag": "v14.0.1"}
        candidate = {"tag": "v15.0.0", "commit": "f" * 40}
        result = release_check.evaluate(current, candidate)
        self.assertEqual(result["status"], "update-available")
        self.assertIs(result["pin"], candidate)
        self.assertEqual(
            release_check.evaluate({"tag": "v15.0.0"}, candidate)["status"], "up-to-date"
        )

    def test_atomic_write_replaces_complete_json(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "upstream.json"
            target.write_text('{"old": true}\n', encoding="utf-8")
            value = {"tag": "v15.0.0", "commit": "f" * 40}
            release_check.atomic_write_json(target, value)
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), value)
            self.assertEqual(list(Path(directory).iterdir()), [target])


if __name__ == "__main__":
    unittest.main()
