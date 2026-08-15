#!/usr/bin/env bash
# Refreshes backend/vendor/orthonym/ from the local Orthonym sibling project.
# Orthonym isn't published on PyPI in the form Orthonym needs (name_tiered(),
# general_fallback), so the backend depends on a vendored source snapshot
# instead of an absolute host path -- Docker builds can't reach outside their
# own build context, and a vendored copy keeps `pip install ./vendor/orthonym`
# working the same in a container as on the host. Re-run this after pulling
# Orthonym changes you want Orthonym to pick up.
set -euo pipefail

SRC="${ORTHONYM_SRC:-/home/kohulan/Orthonym/Project}"
DEST="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/backend/vendor/orthonym"

if [ ! -f "$SRC/pyproject.toml" ]; then
  echo "error: $SRC does not look like the Orthonym project (no pyproject.toml)" >&2
  exit 1
fi

rm -rf "$DEST"
mkdir -p "$DEST"

cp "$SRC/pyproject.toml" "$DEST/"
cp "$SRC/README.md" "$DEST/"
[ -f "$SRC/LICENSE" ] && cp "$SRC/LICENSE" "$DEST/"
[ -f "$SRC/NOTICE" ] && cp "$SRC/NOTICE" "$DEST/"

mkdir -p "$DEST/src"
cp -r "$SRC/src/orthonym" "$DEST/src/"
find "$DEST/src/orthonym" -name '__pycache__' -type d -prune -exec rm -rf {} +
find "$DEST/src/orthonym" -name '*.pyc' -delete

echo "vendored $(find "$DEST/src/orthonym" -name '*.py' | wc -l) .py files + data/ into $DEST"

# orthonym/validation/opsin_grammar.py hard-requires an OPSIN reference
# resource tree at a path computed as 4 parents-up from its own installed
# location + "opsin/opsin-core/src/main/resources/..." (see that file's
# _PROJECT_ROOT). That tree lives as a sibling of src/ in the Orthonym dev
# checkout, NOT inside the orthonym package itself (pyproject.toml's
# packages = ["src/orthonym"] never ships it) -- so any install outside
# a full dev checkout (a vendored copy, a hypothetical real PyPI release)
# fails at import time without it. Vendor just the resources/ subtree (not
# the full opsin-core Java module, no compiled classes/pom.xml needed) so
# scripts/place-opsin-resources.py can put it where the loader expects.
OPSIN_RESOURCES_SRC="$SRC/opsin/opsin-core/src/main/resources"
OPSIN_VENDOR_BASE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/backend/vendor/opsin-resources"
if [ -d "$OPSIN_RESOURCES_SRC" ]; then
  rm -rf "$OPSIN_VENDOR_BASE"
  mkdir -p "$OPSIN_VENDOR_BASE/opsin/opsin-core/src/main"
  cp -r "$OPSIN_RESOURCES_SRC" "$OPSIN_VENDOR_BASE/opsin/opsin-core/src/main/resources"
  echo "vendored OPSIN grammar resources ($(du -sh "$OPSIN_VENDOR_BASE" | cut -f1)) for opsin_grammar.py"
else
  echo "warning: $OPSIN_RESOURCES_SRC not found -- orthonym will fail to import without it" >&2
fi

# orthonym/validation/opsin_roundtrip.py and orthonym/perception/centres_bridge.py
# compute the SAME PROJECT_ROOT (4 parents up) and glob for these two jars there --
# they're what actually runs the real OPSIN/CIP-centres round-trip check (SELF-01).
# Without them (and without jpype/Java), SELF-01 silently "fails open": a name that
# should be suppressed and replaced with an honest fallback can ship as if verified.
# This is NOT a hypothetical -- confirmed by direct A/B testing during Orthonym's own
# Docker work (see DESIGN.md / commit notes), so these are load-bearing, not optional.
for jar in opsin-cli-2.9.0-jar-with-dependencies.jar centres-cli-1.5.jar; do
  if [ -f "$SRC/$jar" ]; then
    cp "$SRC/$jar" "$OPSIN_VENDOR_BASE/$jar"
    echo "vendored $jar ($(du -sh "$OPSIN_VENDOR_BASE/$jar" | cut -f1))"
  else
    echo "warning: $SRC/$jar not found -- SELF-01 round-trip verification will silently fail open without it" >&2
  fi
done
