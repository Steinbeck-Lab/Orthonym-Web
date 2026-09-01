#!/usr/bin/env bash
# Refreshes backend/vendor/openstout/ from the local OpenSTOUT sibling project.
# OpenSTOUT isn't published on PyPI in the form STITCH needs (name_tiered(),
# general_fallback), so the backend depends on a vendored source snapshot
# instead of an absolute host path -- Docker builds can't reach outside their
# own build context, and a vendored copy keeps `pip install ./vendor/openstout`
# working the same in a container as on the host. Re-run this after pulling
# OpenSTOUT changes you want STITCH to pick up.
set -euo pipefail

SRC="${OPENSTOUT_SRC:-/home/kohulan/OpenSTOUT/Project}"
DEST="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/backend/vendor/openstout"

if [ ! -f "$SRC/pyproject.toml" ]; then
  echo "error: $SRC does not look like the OpenSTOUT project (no pyproject.toml)" >&2
  exit 1
fi

rm -rf "$DEST"
mkdir -p "$DEST"

cp "$SRC/pyproject.toml" "$DEST/"
cp "$SRC/README.md" "$DEST/"
[ -f "$SRC/LICENSE" ] && cp "$SRC/LICENSE" "$DEST/"
[ -f "$SRC/NOTICE" ] && cp "$SRC/NOTICE" "$DEST/"

mkdir -p "$DEST/src"
cp -r "$SRC/src/openstout" "$DEST/src/"
find "$DEST/src/openstout" -name '__pycache__' -type d -prune -exec rm -rf {} +
find "$DEST/src/openstout" -name '*.pyc' -delete

echo "vendored $(find "$DEST/src/openstout" -name '*.py' | wc -l) .py files + data/ into $DEST"

# openstout/validation/opsin_grammar.py hard-requires an OPSIN reference
# resource tree at a path computed as 4 parents-up from its own installed
# location + "opsin/opsin-core/src/main/resources/..." (see that file's
# _PROJECT_ROOT). That tree lives as a sibling of src/ in the OpenSTOUT dev
# checkout, NOT inside the openstout package itself (pyproject.toml's
# packages = ["src/openstout"] never ships it) -- so any install outside
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
  echo "warning: $OPSIN_RESOURCES_SRC not found -- openstout will fail to import without it" >&2
fi

# openstout/validation/opsin_roundtrip.py and openstout/perception/centres_bridge.py
# compute the SAME PROJECT_ROOT (4 parents up) and glob for these two jars there --
# they're what actually runs the real OPSIN/CIP-centres round-trip check (SELF-01).
# Without them (and without jpype/Java), SELF-01 silently "fails open": a name that
# should be suppressed and replaced with an honest fallback can ship as if verified.
# This is NOT a hypothetical -- confirmed by direct A/B testing during STITCH's own
# Docker work (see DESIGN.md / commit notes), so these are load-bearing, not optional.
for jar in opsin-cli-2.9.0-jar-with-dependencies.jar centres-cli-1.5.jar; do
  if [ -f "$SRC/$jar" ]; then
    cp "$SRC/$jar" "$OPSIN_VENDOR_BASE/$jar"
    echo "vendored $jar ($(du -sh "$OPSIN_VENDOR_BASE/$jar" | cut -f1))"
  else
    echo "warning: $SRC/$jar not found -- SELF-01 round-trip verification will silently fail open without it" >&2
  fi
done

# --- cache invalidation -----------------------------------------------------
# app/name_cache.py folds a digest of the INSTALLED OpenSTOUT source into every
# cache key, so this refresh invalidates the shared name cache automatically
# once the new snapshot is pip-installed. That is the mechanism; the reminder
# below is the belt to its braces, because the digest is only computed where
# the package can be read (a zipimport or a stripped image falls back to the
# version string alone).
echo
echo "Snapshot refreshed. The name cache invalidates itself via the engine"
echo "fingerprint in app/name_cache.py -- but re-install the package for that"
echo "to take effect:"
echo "    uv pip install -r backend/requirements.txt   (or rebuild the image)"
echo
echo "If naming behaviour changed in a way you want recorded explicitly, bump"
echo "_KEY_VERSION in backend/app/name_cache.py and note why, as v2 does."
