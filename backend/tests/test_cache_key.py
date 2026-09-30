from app import name_cache
from app.core.config import get_settings
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
        # The configured TTL, not merely "some expiry": a hard-coded 1 s
        # would pass a bare `> 0`.
        ttl_limit = get_settings().NAME_CACHE_TTL_SECONDS
        assert ttl_limit - 60 < redis_client.ttl(key) <= ttl_limit
    finally:
        redis_client.delete(key)


def test_a_verified_row_with_no_round_trip_proof_is_not_cached(redis_client):
    """C3: the cache's own guard, tested directly rather than through
    translate_one.

    translate_one can no longer HAND this row to put_cached -- it now
    downgrades a verified status whose round-trip is missing before returning
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
    """best_effort's status claims no round trip of its own -- a null
    roundtrip there is not evidence SELF-01 failed open, so the C3
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
    from app import orthonym_service

    item = orthonym_service.translate_one("CCO", best_effort=True)
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
    from app import orthonym_service, tasks

    item = orthonym_service.translate_one("CCO", best_effort=True)
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


def test_the_key_changes_when_the_engine_source_changes(monkeypatch):
    """key-version-unmechanized: _ENGINE_VERSION cannot invalidate the cache,
    because the upstream Orthonym engine develops on a static "1.0.0" and does
    not bump per change. A vendor refresh could therefore change naming
    behaviour while the key stayed identical, serving names from the old engine
    beside tiers computed by the new one -- the PRODUCT.md principle 2
    violation the key exists to prevent.

    Until now the only defence was a hand-maintained counter with nothing in
    the vendor script or CI to catch a miss, and it HAS been missed: the
    v1 -> v2 bump happened only because that particular refresh broke loudly.

    The key now carries a digest of the installed Orthonym engine source, so a
    refresh invalidates it whether or not anyone remembers.
    """
    before = name_cache.cache_key("CCO", best_effort=True)
    monkeypatch.setattr(name_cache, "_ENGINE_FINGERPRINT", "deadbeef1234")
    assert name_cache.cache_key("CCO", best_effort=True) != before


def test_the_fingerprint_is_stable_across_calls():
    """The other half: it must not change per call, or every request is a
    cache miss and the cache does nothing at all.
    """
    assert name_cache._engine_fingerprint() == name_cache._engine_fingerprint()
    assert name_cache._ENGINE_FINGERPRINT == name_cache._engine_fingerprint()


def test_the_fingerprint_falls_back_rather_than_raising(monkeypatch):
    """A cache key must never fail to build. If the source cannot be read --
    a zipimport, a stripped image -- degrade to the version string alone,
    which is exactly the pre-existing behaviour, and say so loudly enough
    that the manual counter is understood to be load-bearing again.
    """
    monkeypatch.setattr(
        name_cache.pathlib.Path, "rglob", lambda self, pat: (_ for _ in ()).throw(OSError("nope"))
    )
    assert name_cache._engine_fingerprint() == "nofingerprint"


def test_the_fast_and_batch_paths_agree_on_the_cache_key(redis_client):
    """untested-4: spec section 6.1's shared-cache promise is only true if the
    two entry points derive identical keys for the same input. They did not
    once already: the fast path silently stopped routing through the shared
    canonicaliser, so /api/translate and /api/jobs built different strings for
    one molecule and a name computed on one path was re-computed on the other.
    test_cache_key asserted nothing about this, and test_fast_path asserted
    call ORDER only.

    What this test does NOT assert any more: that three spellings of ethanol
    collapse to one key. Owner decision 2026-09-03 (commit 170174b) is to name
    the SMILES the user actually typed, because the Orthonym engine's naming is
    not invariant to atom order -- a molecule can name on the typed ordering and
    abstain on the RDKit-canonical one. So `_canonical_or_error` returns the
    input string untouched on the RDKit path, and two spellings legitimately
    take two cache entries. That costs efficiency, never correctness: the OPSIN
    round-trip compares InChIKeys, which are canonical either way.

    The live invariant is therefore per-input agreement, asserted below, plus
    an explicit pin on the as-typed behaviour -- so re-introducing
    canonicalisation fails here loudly instead of silently reverting an owner
    decision.
    """
    from app.inputs import InputFormat, parse
    from app.main import _canonicalize

    spellings = ["CCO", "OCC", "C(O)C"]

    # BOTH real entry points, not one helper called twice: /api/translate goes
    # through main._canonicalize, and /api/jobs through inputs.parse. The
    # defect being guarded is precisely the two disagreeing, so a test that
    # only exercised one of them would prove nothing.
    for spelling in spellings:
        fast = _canonicalize([spelling], 10)[0].smiles
        batch = parse(spelling.encode(), InputFormat.SMILES_LIST, 10)[0].smiles
        assert fast == batch, (
            f"the two paths build different SMILES for {spelling!r}: "
            f"fast={fast!r} batch={batch!r}, so a name computed on one path "
            f"cannot be reused by the other"
        )
        assert name_cache.cache_key(fast, best_effort=True) == name_cache.cache_key(
            batch, best_effort=True
        ), f"the two paths derive different cache keys for {spelling!r}"

    # The as-typed pin. Three spellings, three keys -- if this ever reads 1,
    # something has started RDKit-canonicalising again and the macrocycle that
    # motivated 170174b will start abstaining once more.
    keys = {
        name_cache.cache_key(_canonicalize([s], 10)[0].smiles, best_effort=True)
        for s in spellings
    }
    assert len(keys) == len(spellings), (
        "the spellings are collapsing to one cache key, so something is "
        "RDKit-canonicalising the input again -- see commit 170174b"
    )


def test_the_fingerprint_follows_the_source_contents(monkeypatch, tmp_path):
    """The fingerprint must change when a source file's CONTENT changes, not
    just when files appear or are renamed; hashing file names would leave
    the cache serving names from an edited engine.
    """
    (tmp_path / "engine.py").write_text("X = 1\n")
    monkeypatch.setattr(name_cache.orthonym, "__file__", str(tmp_path / "__init__.py"))
    before = name_cache._engine_fingerprint()
    assert before != "nofingerprint"
    (tmp_path / "engine.py").write_text("X = 2\n")
    assert name_cache._engine_fingerprint() != before


def test_the_key_embeds_the_manual_key_version(monkeypatch):
    # _KEY_VERSION is the manual half of invalidation; a key that ignores it
    # cannot be flushed by bumping it.
    before = name_cache.cache_key("CCO", best_effort=True)
    monkeypatch.setattr(name_cache, "_KEY_VERSION", "v999")
    after = name_cache.cache_key("CCO", best_effort=True)
    assert after != before
    assert "v999" in after


def test_a_verified_fallback_row_is_cached(redis_client):
    item = ResultItem(
        smiles="CCO",
        status="fallback",
        name="ethanol",
        tier="systematic_verified",
        roundtrip_smiles="CCO",
        roundtrip_match=True,
    )
    key = name_cache.cache_key("CCO", best_effort=True)
    redis_client.delete(key)
    try:
        name_cache.put_cached(item, best_effort=True)
        assert redis_client.exists(key) == 1
        assert name_cache.get_cached("CCO", best_effort=True).status == "fallback"
    finally:
        redis_client.delete(key)
