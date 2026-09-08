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
OPSIN_JAR_VERSION="2.9.0"
OPSIN_JAR="opsin-cli-${OPSIN_JAR_VERSION}-jar-with-dependencies.jar"
OPSIN_JAR_URL="https://github.com/dan2097/opsin/releases/download/${OPSIN_JAR_VERSION}/${OPSIN_JAR}"

# ALWAYS create the destination first. It used to be created only inside the
# `if [ -d ]` below, so on a checkout without the resources tree the directory
# never appeared and the jar copy further down died with a bare
# "cp: cannot create regular file ...: No such file or directory" -- an error
# about the destination that reads like one about the source. Hit on a real
# Ubuntu deploy, 2026-09-08.
mkdir -p "$OPSIN_VENDOR_BASE"

# The jar comes from the Orthonym checkout when it is there, and from OPSIN's
# own public release when it is not. A clone of Orthonym does NOT necessarily
# carry it -- verified on a fresh --depth 1 clone -- and without it SELF-01
# silently "fails open": a name that should be suppressed and replaced with an
# honest fallback ships as if verified. Downloading beats warning.
if [ -f "$SRC/$OPSIN_JAR" ]; then
  cp "$SRC/$OPSIN_JAR" "$OPSIN_VENDOR_BASE/$OPSIN_JAR"
  echo "vendored $OPSIN_JAR from the checkout ($(du -sh "$OPSIN_VENDOR_BASE/$OPSIN_JAR" | cut -f1))"
elif [ ! -f "$OPSIN_VENDOR_BASE/$OPSIN_JAR" ]; then
  echo "$OPSIN_JAR not in the checkout -- downloading the $OPSIN_JAR_VERSION release"
  curl -fsSL -o "$OPSIN_VENDOR_BASE/$OPSIN_JAR" "$OPSIN_JAR_URL"
  echo "downloaded $OPSIN_JAR ($(du -sh "$OPSIN_VENDOR_BASE/$OPSIN_JAR" | cut -f1))"
fi

# The grammar resources: from the checkout if present, otherwise UNPACKED FROM
# THE JAR. orthonym's validation/opsin_grammar.py wants them as real files at
# PROJECT_ROOT + "opsin/opsin-core/src/main/resources/...", and that tree is a
# sibling of src/ in a full Orthonym dev checkout -- a plain clone may not have
# it, and then the package fails at import.
#
# The jar is a complete substitute, not an approximation: its
# uk/ac/cam/ch/wwmm/opsin/{resources/*,opsinbuild.props} entries were diffed
# against a known-good vendored tree and matched exactly, 140 files, nothing
# extra on either side.
OPSIN_RESOURCES_DEST="$OPSIN_VENDOR_BASE/opsin/opsin-core/src/main/resources"
if [ -d "$OPSIN_RESOURCES_SRC" ]; then
  rm -rf "$OPSIN_VENDOR_BASE/opsin"
  mkdir -p "$OPSIN_VENDOR_BASE/opsin/opsin-core/src/main"
  cp -r "$OPSIN_RESOURCES_SRC" "$OPSIN_RESOURCES_DEST"
  echo "vendored OPSIN grammar resources from the checkout ($(du -sh "$OPSIN_VENDOR_BASE/opsin" | cut -f1))"
elif [ -f "$OPSIN_VENDOR_BASE/$OPSIN_JAR" ]; then
  rm -rf "$OPSIN_VENDOR_BASE/opsin"
  mkdir -p "$OPSIN_RESOURCES_DEST"
  ( cd "$OPSIN_RESOURCES_DEST" \
    && unzip -qo "$OPSIN_VENDOR_BASE/$OPSIN_JAR" \
         "uk/ac/cam/ch/wwmm/opsin/resources/*" "uk/ac/cam/ch/wwmm/opsin/opsinbuild.props" )
  n=$(find "$OPSIN_RESOURCES_DEST" -type f | wc -l | tr -d ' ')
  if [ "$n" -lt 100 ]; then
    echo "error: extracted only $n resource files from $OPSIN_JAR -- expected ~140" >&2
    exit 1
  fi
  echo "extracted OPSIN grammar resources from $OPSIN_JAR ($n files, $(du -sh "$OPSIN_VENDOR_BASE/opsin" | cut -f1))"
else
  echo "error: no OPSIN resources and no jar to take them from -- orthonym will fail to import" >&2
  exit 1
fi

# NOTE: the OPSIN jar and the grammar resources are both handled above, and
# centres is not vendored at all any more -- since 2026-09-07 the engine pins
# the tagged 1.2.1 release, which backend/Dockerfile downloads and SHA-checks,
# as it does CDK.

# --- cache invalidation -----------------------------------------------------
# app/name_cache.py folds a digest of the INSTALLED Orthonym source into every
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
