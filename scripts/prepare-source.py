#!/usr/bin/env python3
"""Materialize a verified, patched Parabol build context."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_PIN_KEYS = {
    "repository", "tag", "version", "commit", "archive_url", "archive_sha256"
}
UPSTREAM_REPOSITORY = "https://github.com/ParabolInc/parabol"
REQUIRED_SOURCE_PATHS = (
    "package.json",
    "pnpm-lock.yaml",
    "scripts/generateGraphQLArtifacts.js",
    "scripts/webpack/prod.servers.config.js",
    "scripts/toolboxSrc/preDeploy.ts",
    "packages/server/initPublicPath.ts",
    "docker/images/parabol-ubi/environments/pipeline",
    "docker/images/parabol-ubi/tools/ip-to-server_id/package.json",
    "static/fonts",
)


def load_pin(path: Path) -> dict[str, str]:
    pin = json.loads(path.read_text(encoding="utf-8"))
    if set(pin) != REQUIRED_PIN_KEYS or not all(
        isinstance(value, str) and value for value in pin.values()
    ):
        raise ValueError(
            f"{path} must contain exactly these non-empty strings: {sorted(REQUIRED_PIN_KEYS)}"
        )
    if pin["repository"] != UPSTREAM_REPOSITORY:
        raise ValueError(f"repository must be {UPSTREAM_REPOSITORY}")
    if not re.fullmatch(r"[0-9a-f]{40}", pin["commit"]):
        raise ValueError("upstream commit must be a full lowercase SHA-1")
    if not re.fullmatch(r"[0-9a-f]{64}", pin["archive_sha256"]):
        raise ValueError("archive_sha256 must be a full lowercase SHA-256")
    if pin["tag"] != f"v{pin['version']}":
        raise ValueError("tag/version contract failed")
    expected_url = f"https://codeload.github.com/ParabolInc/parabol/tar.gz/{pin['commit']}"
    if pin["archive_url"] != expected_url:
        raise ValueError("archive URL must address the exact pinned commit")
    return pin


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch_archive(pin: dict[str, str], archive: Path, offline: bool = False) -> None:
    if archive.exists():
        actual = sha256(archive)
        if actual == pin["archive_sha256"]:
            return
        if offline:
            raise ValueError(
                f"cached archive checksum mismatch: expected {pin['archive_sha256']}, got {actual}"
            )
    elif offline:
        raise FileNotFoundError(f"cached archive does not exist: {archive}")

    archive.parent.mkdir(parents=True, exist_ok=True)
    temporary = archive.with_suffix(archive.suffix + ".part")
    temporary.unlink(missing_ok=True)
    request = urllib.request.Request(
        pin["archive_url"], headers={"User-Agent": "parabol-thin-builder/1"}
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response, temporary.open("wb") as output:
            shutil.copyfileobj(response, output)
        actual = sha256(temporary)
        if actual != pin["archive_sha256"]:
            raise ValueError(
                f"archive checksum mismatch: expected {pin['archive_sha256']}, got {actual}"
            )
        os.replace(temporary, archive)
    finally:
        temporary.unlink(missing_ok=True)


def validate_members(members: list[tarfile.TarInfo], root_name: str) -> None:
    prefix = root_name + "/"
    names: set[str] = set()
    for member in members:
        path = PurePosixPath(member.name)
        if member.name in names:
            raise ValueError(f"duplicate archive member: {member.name}")
        names.add(member.name)
        if member.name != root_name and not member.name.startswith(prefix):
            raise ValueError(f"archive member escapes expected root: {member.name}")
        if path.is_absolute() or ".." in path.parts or member.isdev() or member.isfifo():
            raise ValueError(f"unsafe archive member: {member.name}")
        if member.issym() or member.islnk():
            target = PurePosixPath(member.linkname)
            if target.is_absolute() or ".." in target.parts:
                raise ValueError(f"unsafe archive link: {member.name} -> {member.linkname}")


def validate_source_contract(source: Path, pin: dict[str, str]) -> None:
    package_path = source / "package.json"
    try:
        package = json.loads(package_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as error:
        raise ValueError("archive is missing a valid package.json") from error
    if package.get("name") != "parabol-action":
        raise ValueError(f"unexpected package name: {package.get('name')!r}")
    if package.get("version") != pin["version"]:
        raise ValueError(f"package version mismatch: {package.get('version')!r}")
    for relative in REQUIRED_SOURCE_PATHS:
        if not (source / relative).exists():
            raise ValueError(f"archive is missing required source path: {relative}")


def apply_patches(source: Path) -> None:
    patches = sorted((ROOT / "patches").glob("*.patch"))
    if not patches:
        raise ValueError("no downstream patches found")
    for patch in patches:
        subprocess.run(
            ["git", "apply", "--check", "--unidiff-zero", "--whitespace=error-all", str(patch)],
            cwd=source,
            check=True,
        )
        subprocess.run(
            ["git", "apply", "--unidiff-zero", "--whitespace=error-all", str(patch)], cwd=source, check=True
        )


def copy_overlay(source: Path) -> None:
    overlay = ROOT / "overlay"
    files = sorted(path for path in overlay.rglob("*") if path.is_file())
    if not files:
        raise ValueError("build overlay is empty")
    for item in files:
        relative = item.relative_to(overlay)
        target = source / relative
        if target.exists():
            raise ValueError(f"overlay refuses to replace upstream path: {relative}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(item, target)
        shutil.copymode(item, target)


def normalize_context(source: Path) -> None:
    """Remove host-time variance while preserving executable modes."""
    for path in sorted(source.rglob("*"), reverse=True):
        if not path.is_symlink():
            os.utime(path, (0, 0), follow_symlinks=False)
    os.utime(source, (0, 0))


def materialize(pin_path: Path, output: Path, archive: Path, offline: bool = False) -> None:
    pin = load_pin(pin_path)
    fetch_archive(pin, archive, offline=offline)
    actual = sha256(archive)
    if actual != pin["archive_sha256"]:
        raise ValueError(
            f"cached archive checksum mismatch: expected {pin['archive_sha256']}, got {actual}"
        )
    if output.exists():
        raise FileExistsError(f"output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="parabol-prepare-", dir=output.parent) as temporary:
        temporary_path = Path(temporary)
        root_name = f"parabol-{pin['commit']}"
        with tarfile.open(archive, "r:gz") as bundle:
            members = bundle.getmembers()
            validate_members(members, root_name)
            bundle.extractall(temporary_path, filter="data")
        source = temporary_path / root_name
        if not source.is_dir():
            raise ValueError(f"archive did not create expected root: {root_name}")
        validate_source_contract(source, pin)
        apply_patches(source)
        copy_overlay(source)
        dockerfile = source / "docker/selfhost/Dockerfile"
        text = dockerfile.read_text(encoding="utf-8")
        text = text.replace("@@SOURCE_COMMIT@@", pin["commit"]).replace(
            "@@SOURCE_TAG@@", pin["tag"]
        )
        if "@@SOURCE_" in text:
            raise ValueError("unresolved Dockerfile template placeholder")
        dockerfile.write_text(text, encoding="utf-8")
        (source / ".builder-source.json").write_text(
            json.dumps(pin, indent=2) + "\n", encoding="utf-8"
        )
        normalize_context(source)
        os.replace(source, output)
    print(f"prepared {pin['tag']} ({pin['commit']}) at {output}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pin", type=Path, default=ROOT / "upstream.json")
    parser.add_argument("--archive", type=Path, default=ROOT / ".cache" / "upstream.tar.gz")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--offline", action="store_true", help="require an already-cached valid archive"
    )
    args = parser.parse_args()
    materialize(
        args.pin.resolve(), args.output.resolve(), args.archive.resolve(), offline=args.offline
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"prepare-source: {error}", file=sys.stderr)
        raise SystemExit(1)
