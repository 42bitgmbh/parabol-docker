#!/usr/bin/env python3
import importlib.util
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("prepare_source", ROOT / "scripts/prepare-source.py")
assert spec is not None and spec.loader is not None
prepare_source = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare_source)


class PrepareSourceTests(unittest.TestCase):
    def test_current_pin_has_exact_contract(self):
        pin = prepare_source.load_pin(ROOT / "upstream.json")
        self.assertEqual(pin["tag"], f"v{pin['version']}")
        self.assertIn(pin["commit"], pin["archive_url"])

    def test_pin_rejects_unexpected_repository_and_keys(self):
        pin = json.loads((ROOT / "upstream.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "pin.json"
            pin["repository"] = "https://example.test/not-parabol"
            target.write_text(json.dumps(pin), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "repository must"):
                prepare_source.load_pin(target)
            pin["repository"] = prepare_source.UPSTREAM_REPOSITORY
            pin["unexpected"] = "value"
            target.write_text(json.dumps(pin), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "exactly"):
                prepare_source.load_pin(target)

    def test_archive_members_reject_traversal_duplicates_and_unsafe_links(self):
        root = "parabol-" + "a" * 40
        safe = tarfile.TarInfo(f"{root}/package.json")
        prepare_source.validate_members([safe], root)
        traversal = tarfile.TarInfo(f"{root}/../escape")
        with self.assertRaisesRegex(ValueError, "unsafe"):
            prepare_source.validate_members([traversal], root)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            prepare_source.validate_members([safe, safe], root)
        link = tarfile.TarInfo(f"{root}/link")
        link.type = tarfile.SYMTYPE
        link.linkname = "../../escape"
        with self.assertRaisesRegex(ValueError, "unsafe archive link"):
            prepare_source.validate_members([link], root)

    def test_offline_cache_rejects_missing_or_wrong_bytes_without_network(self):
        pin = prepare_source.load_pin(ROOT / "upstream.json")
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "archive.tar.gz"
            with self.assertRaises(FileNotFoundError):
                prepare_source.fetch_archive(pin, archive, offline=True)
            archive.write_bytes(b"wrong")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                prepare_source.fetch_archive(pin, archive, offline=True)


if __name__ == "__main__":
    unittest.main()
