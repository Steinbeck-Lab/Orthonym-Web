"""Cache a computed name, keyed so a stale one can never be served.

PRODUCT.md principle 2 says never overstate measured accuracy. A cache is
the easy way to violate it: serve a name an older engine produced and the
displayed tier no longer describes the engine that is installed. So the key
embeds the OpenSTOUT version and the namer flags that change the answer. A
version bump therefore invalidates everything with no migration step.
"""

from __future__ import annotations

import hashlib

import openstout

from app.core.config import get_settings
from app.redis_store import get_redis
from app.schemas import ResultItem

# BUMP THIS whenever the vendored OpenSTOUT snapshot is refreshed.
#
# The key embeds openstout.__version__ so a release bump invalidates the
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
_KEY_VERSION = "v2"
_ENGINE_VERSION = openstout.__version__

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
        f"stitch:name:{_KEY_VERSION}:{_ENGINE_VERSION}:{flags}:{digest}"
    )


def get_cached(canonical_smiles: str, best_effort: bool) -> ResultItem | None:
    raw = get_redis().get(cache_key(canonical_smiles, best_effort))
    if raw is None:
        return None
    return ResultItem.model_validate_json(raw)


def put_cached(item: ResultItem, best_effort: bool) -> None:
    if item.status not in _CACHEABLE:
        return
    settings = get_settings()
    get_redis().set(
        cache_key(item.smiles, best_effort),
        item.model_dump_json(),
        ex=settings.NAME_CACHE_TTL_SECONDS,
    )
