#!/usr/bin/env python3
"""Discover and validate the newest stable Parabol GitHub release."""
from __future__ import annotations

import argparse
from collections.abc import Callable
import hashlib
import io
import json
import os
from pathlib import Path
import re
import tarfile
import tempfile
from typing import Any
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
API = "https://api.github.com/repos/ParabolInc/parabol"
REPOSITORY = "https://github.com/ParabolInc/parabol"
JsonGetter = Callable[[str], Any]
Fetcher = Callable[[str], bytes]


def semver(tag: str) -> tuple[int, int, int] | None:
    match = re.fullmatch(r"v(\d+)\.(\d+)\.(\d+)", tag)
    if match is None:
        return None
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch)


def request_json(url: str) -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "parabol-thin-builder/1",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    # Unauthenticated API calls from shared CI runners hit the 60/hour limit.
    if token := os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def download(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "parabol-thin-builder/1"})
    with urllib.request.urlopen(request, timeout=180) as response:
        return response.read()


def stable_release(releases: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = [
        release
        for release in releases
        if not release.get("draft")
        and not release.get("prerelease")
        and semver(str(release.get("tag_name", ""))) is not None
    ]
    if not candidates:
        raise ValueError("GitHub returned no stable semantic-version releases")
    return max(candidates, key=lambda release: semver(str(release["tag_name"])) or (-1, -1, -1))


def peel_commit(tag: str, get_json: JsonGetter = request_json) -> str:
    response = get_json(f"{API}/git/ref/tags/{tag}")
    obj = response["object"]
    seen: set[str] = set()
    for _ in range(8):
        object_type = obj.get("type")
        sha = obj.get("sha", "")
        if not re.fullmatch(r"[0-9a-f]{40}", sha):
            raise ValueError("GitHub returned a malformed tag object SHA")
        if sha in seen:
            raise ValueError("annotated tag chain contains a cycle")
        seen.add(sha)
        if object_type == "commit":
            return sha
        if object_type != "tag":
            raise ValueError(f"tag resolves to unsupported object type {object_type!r}")
        obj = get_json(f"{API}/git/tags/{sha}")["object"]
    raise ValueError("annotated tag chain is unexpectedly deep")


def validate_archive(tag: str, commit: str, payload: bytes) -> str:
    expected_root = f"parabol-{commit}"
    package_name = f"{expected_root}/package.json"
    try:
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as bundle:
            names = bundle.getnames()
            if any(name != expected_root and not name.startswith(expected_root + "/") for name in names):
                raise ValueError("archive contains a path outside the expected commit root")
            package_file = bundle.extractfile(package_name)
            if package_file is None:
                raise ValueError("archive package.json is not a regular file")
            package = json.load(package_file)
    except (tarfile.TarError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise ValueError("archive does not have a valid expected commit root/package.json") from error
    if package.get("name") != "parabol-action":
        raise ValueError("archive package name is not parabol-action")
    if package.get("version") != tag.removeprefix("v"):
        raise ValueError("release tag and package version disagree")
    return hashlib.sha256(payload).hexdigest()


def discover(get_json: JsonGetter = request_json, fetch: Fetcher = download) -> dict[str, str]:
    releases = get_json(f"{API}/releases?per_page=100")
    if not isinstance(releases, list):
        raise ValueError("GitHub releases response was not a list")
    release = stable_release(releases)
    tag = str(release["tag_name"])
    commit = peel_commit(tag, get_json)
    archive_url = f"https://codeload.github.com/ParabolInc/parabol/tar.gz/{commit}"
    digest = validate_archive(tag, commit, fetch(archive_url))
    return {
        "repository": REPOSITORY,
        "tag": tag,
        "version": tag.removeprefix("v"),
        "commit": commit,
        "archive_url": archive_url,
        "archive_sha256": digest,
    }


def atomic_write_json(path: Path, value: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(value, output, indent=2)
            output.write("\n")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def evaluate(current: dict[str, str], candidate: dict[str, str]) -> dict[str, Any]:
    current_version = semver(current.get("tag", ""))
    candidate_version = semver(candidate.get("tag", ""))
    if current_version is None:
        raise ValueError("current pin has a malformed stable tag")
    if candidate_version is None:
        raise ValueError("candidate has a malformed stable tag")
    if candidate_version <= current_version:
        return {
            "status": "up-to-date",
            "current": current["tag"],
            "latest": candidate["tag"],
        }
    return {
        "status": "update-available",
        "current": current["tag"],
        "latest": candidate["tag"],
        "pin": candidate,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pin", type=Path, default=ROOT / "upstream.json")
    parser.add_argument("--write", action="store_true", help="atomically write a validated newer pin")
    parser.add_argument("--dry-run", action="store_true", help="never write, even with --write")
    args = parser.parse_args()
    current = json.loads(args.pin.read_text(encoding="utf-8"))
    candidate = discover()
    result = evaluate(current, candidate)
    if result["status"] == "update-available" and args.write and not args.dry_run:
        atomic_write_json(args.pin, candidate)
        result["written"] = True
    else:
        result["written"] = False
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
