from app import name_cache
from app.schemas import ResultItem


def test_key_embeds_the_openstout_version():
    import openstout

    key = name_cache.cache_key("CCO", best_effort=True)
    assert openstout.__version__ in key


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
    from app import openstout_service

    item = openstout_service.translate_one("CCO", best_effort=True)
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


def test_the_cached_payload_carries_no_depiction(redis_client):
    """I9: the picture was 94% of every cache entry, at a 7-day TTL.

    Measured on ethanol, the smallest realistic molecule: 2839 bytes cached,
    of which 2673 is depiction_svg. A 10,000-molecule job seeded ~28 MB of
    7-day cache against a 2 GB volatile-lru limit -- almost all of it
    pictures the batch path never draws, since BatchRow drops the SVG
    deliberately (schemas.py, spec section 6.3: "at roughly 5 kB per row an
    SVG would make a 5,000-row job 25-50 MB in Redis instead of 2-5 MB").
    That made the cache the single largest source of the eviction pressure
    behind the partial-results and 404-instead-of-410 failures.
    """
    from app import openstout_service

    item = openstout_service.translate_one("CCO", best_effort=True)
    assert item.depiction_svg is not None, "precondition: this row has a picture"

    key = name_cache.cache_key(item.smiles, best_effort=True)
    redis_client.delete(key)
    try:
        name_cache.put_cached(item, best_effort=True)
        raw = redis_client.get(key)
        assert raw is not None, "the row was not cached at all"
        assert "depiction_svg" not in raw or '"depiction_svg":null' in raw, (
            f"the depiction is still in the cached payload ({len(raw)} bytes)"
        )
        assert len(raw) < 600, (
            f"cached entry is {len(raw)} bytes; the picture is still in there"
        )
    finally:
        redis_client.delete(key)


def test_a_cache_hit_still_comes_back_with_a_picture(redis_client):
    """The other half, and the reason the redraw branch in tasks.py must NOT
    be deleted as dead code.

    It is dead only BECAUSE the picture is cached. Stop caching it and that
    branch becomes the thing that keeps /api/translate's response shape
    identical on a cache hit and a cache miss -- delete both together and the
    fast path silently starts returning results with no structure image.
    """
    from app import openstout_service, tasks

    item = openstout_service.translate_one("CCO", best_effort=True)
    key = name_cache.cache_key("CCO", best_effort=True)
    redis_client.delete(key)
    try:
        name_cache.put_cached(item, best_effort=True)
        assert name_cache.get_cached("CCO", best_effort=True).depiction_svg is None

        rows = tasks.translate_fast.run(
            [{"index": 0, "raw_input": "CCO", "input_id": None, "smiles": "CCO", "error": None}],
            True,
        )
        assert rows[0]["depiction_svg"], (
            "a cache hit returned no picture; the response shape now differs "
            "between a hit and a miss"
        )
    finally:
        redis_client.delete(key)


def test_an_abstain_is_cached(redis_client):
    """deferred-4: _CACHEABLE includes "abstain" but the string appeared
    nowhere in this file, so dropping it re-ran the full OPSIN pipeline on
    every abstain request with the suite still green.

    An abstain is expensive to reach -- it means both the primary and the
    escalated namer ran and neither produced a name -- and it is a perfectly
    stable answer, so it is exactly the result most worth caching.
    """
    item = ResultItem(
        smiles="[Xe]",
        status="abstain",
        name=None,
        tier="abstain",
        formula="Xe",
        limit_code=None,
        error=None,
        depiction_svg=None,
        roundtrip_smiles=None,
        roundtrip_match=None,
    )
    key = name_cache.cache_key(item.smiles, best_effort=True)
    redis_client.delete(key)
    try:
        name_cache.put_cached(item, best_effort=True)
        assert redis_client.exists(key) == 1, (
            "an abstain was not cached, so every repeat request re-runs both "
            "namers for an answer that cannot change"
        )
        assert name_cache.get_cached(item.smiles, best_effort=True).status == "abstain"
    finally:
        redis_client.delete(key)
