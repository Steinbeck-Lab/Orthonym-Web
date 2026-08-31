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
        tier="T1",
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
