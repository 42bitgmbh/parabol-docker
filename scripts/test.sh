#!/bin/sh
# Fast checks that need no Docker: unit tests, then patch the pinned source and run the overlay tests.
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d "${TMPDIR:-/tmp}/parabol-builder-test.XXXXXX")
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

python3 -m unittest discover -s "$ROOT/tests" -v
python3 "$ROOT/scripts/prepare-source.py" --output "$TMP/context"
node --test "$TMP/context/docker/selfhost/build.test.cjs"
node --experimental-strip-types --test "$TMP/context/docker/selfhost/resolve-public-path.test.mjs"
sh -n "$TMP/context/docker/selfhost/entrypoint.sh"
