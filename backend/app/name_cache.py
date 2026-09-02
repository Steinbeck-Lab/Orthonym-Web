"""Cache a computed name, keyed so a stale one can never be served.

PRODUCT.md principle 2 says never overstate measured accuracy. A cache is
the easy way to violate it: serve a name an older engine produced and the
displayed tier no longer describes the engine that is installed. So the key
embeds the Orthonym version and the namer flags that change the answer. A
version bump therefore invalidates everything with no migration step.
"""

from __future__ import annotations

import hashlib
import logging
import pathlib

import orthonym

from app.core.config import get_settings
from app.redis_store import get_redis
from app.schemas import VERIFIED_STATUSES, ResultItem

# BUMP THIS whenever the vendored Orthonym snapshot is refreshed.
#
# The key embeds orthonym.__version__ so a release bump invalidates the
# cache automatically -- but upstream develops on a static "1.0.0" and does
# not bump per change, so a vendor refresh can change naming behaviour while
# the version string stays identical. That would serve names from the old
# engine beside tiers computed by the new one, which is exactly the
# PRODUCT.md principle 2 violation this key exists to prevent. The version
# string alone is therefore NOT sufficient; this counter is the manual half.
#
# v2: 2026-08-31 vendor refresh -- upstream replaced the whole tier
#     vocabulary (T1/T3/T4/T5 -> pin_verified/systematic_verified/
#     best_effort/abstain) and changed best-effort gating.
logger = logging.getLogger(__name__)

# v3 (2026-09-02): the visible round-trip check changed from comparing
# canonical SMILES to comparing full standard InChIKeys, so every cached
# roundtrip_match computed under v2 may carry the old verdict -- zwitterionic
# glycine was cached as a MISMATCH on a correct PIN. The engine fingerprint
# below cannot see a change in THIS app's code, which is exactly what this
# manual counter is for.
_KEY_VERSION = "v3"
_ENGINE_VERSION = orthonym.__version__


def _engine_fingerprint() -> str:
    """A digest of the Orthonym source actually installed in this process.

    This is what makes the cache key self-invalidating, and it is why the
    manual counter above is now a belt rather than the only thing holding the
    trousers up (audit item key-version-unmechanized). Upstream develops on a
    static "1.0.0", so _ENGINE_VERSION cannot notice a vendor refresh -- and
    the counter above depends on a human remembering, with nothing in the
    vendor script or CI to catch a miss. It has already been missed once: the
    v1 -> v2 bump was made only because the tier rename happened to break
    loudly.

    Hashing the INSTALLED package rather than backend/vendor/orthonym is
    deliberate: what matters is the code that will actually name molecules in
    this process, which in a container is the copy pip installed. Measured at
    40 ms over 253 files, paid once at import, never per request.

    Falls back to the bare version string if the source cannot be read (a
    zipimport, a stripped image). That is the pre-existing behaviour, no
    worse than before -- and _KEY_VERSION still covers it.
    """
    try:
        root = pathlib.Path(orthonym.__file__).resolve().parent
        digest = hashlib.sha256()
        for path in sorted(root.rglob("*.py")):
            digest.update(path.read_bytes())
        return digest.hexdigest()[:12]
    except Exception:  # noqa: BLE001 - a cache key must never fail to build
        logger.warning(
            "name_cache: could not fingerprint the installed Orthonym "
            "source; falling back to the version string alone. A vendor "
            "refresh will NOT invalidate the cache automatically -- bump "
            "_KEY_VERSION by hand.",
        )
        return "nofingerprint"


_ENGINE_FINGERPRINT = _engine_fingerprint()

# Statuses worth keeping. "error" is about the input, not the engine's
# verdict: caching it would hide a later fix and spend memory on garbage.
_CACHEABLE = {"pin", "fallback", "best_effort", "abstain"}



def cache_key(canonical_smiles: str, best_effort: bool) -> str:
    """`best_effort` is part of the key because it decides whether the
    escalated namer runs at all -- and therefore whether a molecule can come
    back "best_effort". Sharing an entry across the two serves a wrong tier.
    """
    flags = f"be={int(best_effort)}"
    digest = hashlib.sha256(canonical_smiles.encode("utf-8")).hexdigest()
    return (
        f"orthonym:name:{_KEY_VERSION}:{_ENGINE_VERSION}:"
        f"{_ENGINE_FINGERPRINT}:{flags}:{digest}"
    )


def get_cached(canonical_smiles: str, best_effort: bool) -> ResultItem | None:
    raw = get_redis().get(cache_key(canonical_smiles, best_effort))
    if raw is None:
        return None
    return ResultItem.model_validate_json(raw)


def put_cached(item: ResultItem, best_effort: bool) -> None:
    if item.status not in _CACHEABLE:
        return
    if item.status in VERIFIED_STATUSES and item.roundtrip_smiles is None:
        # This is the fingerprint of SELF-01 having failed open, not merely
        # a missing nicety. _roundtrip_check (orthonym_service.py) calls
        # the SAME opsin_parse() that Orthonym's internal SELF-01 gate
        # uses, so for a tier that CLAIMS verification (pin_verified /
        # systematic_verified -> "pin"/"fallback" here), "OPSIN is
        # reachable but cannot interpret this name" cannot happen -- if it
        # could interpret the PIN candidate, SELF-01 would have used that
        # same answer to verify or suppress it. So roundtrip_smiles is
        # None here if and only if OPSIN itself was unreachable, which
        # means SELF-01 could not suppress a bogus PIN either and just
        # shipped it, mislabelled as verified. Caching that row would
        # persist the mislabel for NAME_CACHE_TTL_SECONDS (7 days) and keep
        # serving it long after OPSIN is restored (final review report,
        # C3). best_effort is exempt: a null round-trip there is exactly
        # what "OPSIN-unverified" means, not a failure. abstain is exempt
        # too: it claims no name at all.
        return
    settings = get_settings()
    get_redis().set(
        cache_key(item.smiles, best_effort),
        # exclude the picture: measured at 94% of the payload (2673 of 2839
        # bytes on ethanol), for something the batch path never draws --
        # BatchRow drops it deliberately and spec section 6.3 spells out why.
        # A 10,000-molecule job seeded ~28 MB of 7-day cache; it now seeds
        # ~1.7 MB. The fast path, which DOES want a picture, redraws it on a
        # cache hit (tasks.translate_fast) -- that branch is what keeps the
        # response shape identical on a hit and a miss, so it is load-bearing
        # now rather than dead.
        item.model_dump_json(exclude={"depiction_svg"}),
        ex=settings.NAME_CACHE_TTL_SECONDS,
    )
