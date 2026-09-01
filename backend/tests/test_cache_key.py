from app import name_cache
from app.schemas import ResultItem


def test_key_embeds_the_orthonym_version():
    import orthonym

    key = name_cache.cache_key("CCO", best_effort=True)
    assert orthonym.__version__ in key


def test_a_version_bump_changes_the_key(monkeypatch):
    # This is what makes caching safe against PRODUCT.md principle 2: a name
    # computed by an older engine can never be served by a newer one.
    before = name_cache.cache_key("CCO", best_effort=True)
    monkeypatch.setattr(name_cache, "_ENGINE_VERSION", "99.0.0", raising=True)
    assert name_cache.cache_key("CCO", best_effort=True) != before


def test_best_effort_changes_the_key():
    # best_effort decides whether the escalated namer runs, and therefore
    # whether a molecule can come back "best_effort" at all. Sharing a cache
    # entry across the two would serve the wrong tier.
    assert name_cache.cache_key("CCO", best_effort=True) != name_cache.cache_key(
        "CCO", best_effort=False
    )


def test_different_molecules_get_different_keys():
    assert name_cache.cache_key("CCO", True) != name_cache.cache_key("CCC", True)


def test_round_trip_through_redis(redis_client):
    item = ResultItem(
        smiles="CCO",
        status="pin",
        name="ethanol",
        tier="pin_verified",
        roundtrip_smiles="CCO",
        roundtrip_match=True,
    )
    key = name_cache.cache_key("CCO", best_effort=True)
    redis_client.delete(key)
    try:
        assert name_cache.get_cached("CCO", best_effort=True) is None
        name_cache.put_cached(item, best_effort=True)
        got = name_cache.get_cached("CCO", best_effort=True)
        assert got is not None
        assert got.name == "ethanol"
        assert got.status == "pin"
        assert redis_client.ttl(key) > 0
    finally:
        redis_client.delete(key)


def test_a_verified_row_with_no_round_trip_proof_is_not_cached(redis_client):
    """C3: the cache's own guard, tested directly rather than through
    translate_one.

    translate_one can no longer HAND this row to put_cached -- it now
    downgrades a verified tier whose round-trip is missing before returning
    it (see tests/test_tier_honesty.py). This test therefore builds the
    mislabelled row itself, which is the honest way to keep testing a
    defence-in-depth guard: put_cached is module-level and public, the
    downgrade and the cache guard are independent, and a future caller that
    reaches put_cached by some other route must still be refused.

    Constructing the row directly is also what keeps this test meaningful
    rather than vacuous: routing it through translate_one would now assert
    only that the downgrade works, which is a different test's job.
    """
    item = ResultItem(
        smiles="CCO",
        status="pin",
        name="ethanol",
        tier="pin_verified",
        formula=None,
        limit_code=None,
        error=None,
        depiction_svg=None,
        roundtrip_smiles=None,   # OPSIN was unreachable; SELF-01 failed open
        roundtrip_match=None,
    )

    key = name_cache.cache_key(item.smiles, best_effort=True)
    redis_client.delete(key)
    try:
        name_cache.put_cached(item, best_effort=True)
        assert redis_client.exists(key) == 0, (
            "a pin with no round-trip proof was cached anyway, persisting the "
            "mislabel for a 7-day TTL"
        )
    finally:
        redis_client.delete(key)


def test_a_genuinely_verified_pin_is_still_cached(redis_client):
    """Vacuity guard for the fix above: a real round-trip proof must still
    be cached, so the fix is not simply disabling the cache outright.
    """
    from app import orthonym_service

    item = orthonym_service.translate_one("CCO", best_effort=True)
    assert item.status == "pin"
    assert item.roundtrip_smiles is not None

    key = name_cache.cache_key(item.smiles, best_effort=True)
    redis_client.delete(key)
    try:
        name_cache.put_cached(item, best_effort=True)
        assert redis_client.exists(key) == 1
    finally:
        redis_client.delete(key)


def test_a_best_effort_row_with_no_roundtrip_is_still_cached(redis_client):
    """best_effort's whole point is "a real name, OPSIN-unverified" -- a
    null roundtrip there is not evidence SELF-01 failed open, so the C3
    guard (scoped to pin/fallback only) must not evict it too.
    """
    item = ResultItem(
        smiles="CCO",
        status="best_effort",
        name="ethanol",
        tier="best_effort",
        roundtrip_smiles=None,
        roundtrip_match=None,
    )
    key = name_cache.cache_key(item.smiles, best_effort=True)
    redis_client.delete(key)
    try:
        name_cache.put_cached(item, best_effort=True)
        assert redis_client.exists(key) == 1
    finally:
        redis_client.delete(key)


def test_error_rows_are_not_cached(redis_client):
    item = ResultItem(
        smiles="bad", status="error", error="Could not parse this SMILES string"
    )
    key = name_cache.cache_key("bad", best_effort=True)
    redis_client.delete(key)
    try:
        name_cache.put_cached(item, best_effort=True)
        # An error is about the input, not about the engine's verdict.
        # Caching it would hide a later fix and waste memory on garbage.
        assert redis_client.exists(key) == 0
    finally:
        redis_client.delete(key)
