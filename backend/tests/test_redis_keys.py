import time

from app import redis_store


def test_keys_are_namespaced_and_stable():
    assert redis_store.job_meta_key("abc") == "orthonym:job:abc:meta"
    assert redis_store.job_rows_key("abc") == "orthonym:job:abc:rows"
    assert redis_store.job_chunk_key("abc", 3) == "orthonym:job:abc:chunk:3"


def test_create_job_records_totals_and_status(redis_client, job_id):
    redis_store.create_job(job_id, total=50, fmt="sdf", client_ip="1.2.3.4")
    meta = redis_store.read_job_meta(job_id)
    assert meta["status"] == "queued"
    assert meta["total"] == "50"
    assert meta["done"] == "0"
    assert meta["failed"] == "0"
    assert meta["fmt"] == "sdf"


def test_read_job_meta_returns_none_for_an_unknown_job(redis_client):
    assert redis_store.read_job_meta("no-such-job") is None


def test_bump_job_done_accumulates(redis_client, job_id):
    # Two DIFFERENT chunk indices -- accumulation across chunks is the
    # property under test; the SAME index accumulating too would be the
    # I1 double-count bug (covered separately below).
    redis_store.create_job(job_id, total=10, fmt="smiles_list", client_ip="::1")
    redis_store.bump_job_done(job_id, index=0, done=4, failed=1)
    redis_store.bump_job_done(job_id, index=1, done=3, failed=0)
    meta = redis_store.read_job_meta(job_id)
    assert meta["done"] == "7"
    assert meta["failed"] == "1"


def test_bump_job_done_tallies_tiers_separately_from_failed(redis_client, job_id):
    # The bug this covers: the batch panel reported `failed` only, so a job
    # whose molecules the engine honestly DECLINED reported "0 failed" and
    # looked like a clean run. An abstain is a successful row, so it must be
    # counted, and counted somewhere other than `failed`.
    redis_store.create_job(job_id, total=6, fmt="smiles_list", client_ip="::1")
    redis_store.bump_job_done(
        job_id,
        index=0,
        done=3,
        failed=0,
        counts={"pin": 2, "abstain": 1, "fallback": 0},
    )
    redis_store.bump_job_done(
        job_id, index=1, done=3, failed=1, counts={"abstain": 2, "error": 1}
    )

    meta = redis_store.read_job_meta(job_id)
    counts = redis_store.job_tier_counts(meta)

    assert counts == {"pin": 2, "abstain": 3, "error": 1}
    # The whole point: three abstains did NOT become three failures.
    assert meta["failed"] == "1"
    # A tier with no rows is absent, not 0 -- "none yet" must not read as
    # "counted, none found". The zero is handed in on purpose: a writer that
    # stored it would make this field appear.
    assert "fallback" not in counts


def test_a_redelivered_chunk_does_not_double_count_its_tiers(redis_client, job_id):
    # Same guard as done/failed: one hsetnx marker gates the whole pipeline,
    # so task_acks_late redelivery cannot inflate the tally either.
    redis_store.create_job(job_id, total=2, fmt="smiles_list", client_ip="::1")
    redis_store.bump_job_done(job_id, index=0, done=2, failed=0, counts={"pin": 2})
    redis_store.bump_job_done(job_id, index=0, done=2, failed=0, counts={"pin": 2})

    counts = redis_store.job_tier_counts(redis_store.read_job_meta(job_id))
    assert counts == {"pin": 2}


def test_job_tier_counts_ignores_the_other_meta_fields(redis_client, job_id):
    # The tally shares the meta hash with `done`, `failed`, `owner`,
    # `bumped:{index}` and friends. A prefix that leaked any of those into
    # the API response would publish the owner token.
    redis_store.create_job(job_id, total=1, fmt="smiles_list", client_ip="::1")
    redis_store.bump_job_done(job_id, index=0, done=1, failed=0, counts={"pin": 1})

    meta = redis_store.read_job_meta(job_id)
    assert redis_store.job_tier_counts(meta) == {"pin": 1}


def test_assemble_rows_orders_chunks_and_cleans_them_up(redis_client, job_id):
    redis_store.create_job(job_id, total=4, fmt="smiles_list", client_ip="::1")
    # Written out of order on purpose: chunks finish out of order.
    redis_store.write_chunk(job_id, 1, [{"index": 2}, {"index": 3}])
    redis_store.write_chunk(job_id, 0, [{"index": 0}, {"index": 1}])

    written = redis_store.assemble_rows(job_id, n_chunks=2)

    assert written == 4
    rows = redis_store.read_rows(job_id, offset=0, limit=10)
    assert [r["index"] for r in rows] == [0, 1, 2, 3]
    assert redis_client.exists(redis_store.job_chunk_key(job_id, 0)) == 0
    assert redis_client.exists(redis_store.job_chunk_key(job_id, 1)) == 0


def test_assembling_twice_does_not_duplicate_rows(redis_client, job_id):
    # A redelivered close runs assemble_rows again on a job that already has
    # rows; appending to the old list would double every row.
    redis_store.create_job(job_id, total=2, fmt="smiles_list", client_ip="::1")
    redis_store.write_chunk(job_id, 0, [{"index": 0}, {"index": 1}])
    redis_store.assemble_rows(job_id, n_chunks=1)
    redis_store.write_chunk(job_id, 0, [{"index": 0}, {"index": 1}])
    redis_store.assemble_rows(job_id, n_chunks=1)

    rows = redis_store.read_rows(job_id, offset=0, limit=10)
    assert [r["index"] for r in rows] == [0, 1]


def test_assembled_rows_and_meta_both_carry_a_ttl(redis_client, job_id):
    redis_store.create_job(job_id, total=1, fmt="smiles_list", client_ip="::1")
    # Checked before assembling: assemble_rows also arms the meta key, so a
    # create_job that forgot its own expiry would otherwise be hidden by it.
    assert redis_client.ttl(redis_store.job_meta_key(job_id)) > 0
    redis_store.write_chunk(job_id, 0, [{"index": 0}])
    redis_store.assemble_rows(job_id, n_chunks=1)

    # A job that never expires would grow Redis without bound, and the
    # no-database rule depends on results being transient.
    assert redis_client.ttl(redis_store.job_rows_key(job_id)) > 0
    assert redis_client.ttl(redis_store.job_meta_key(job_id)) > 0


def test_assemble_rows_retags_a_meta_key_that_lost_its_ttl(redis_client, job_id):
    # The other half of the pair above: create_job's expiry would satisfy a
    # bare "has a TTL" check, so strip it first and let assemble_rows be the
    # only thing that can put it back.
    redis_store.create_job(job_id, total=1, fmt="smiles_list", client_ip="::1")
    redis_store.write_chunk(job_id, 0, [{"index": 0}])
    key = redis_store.job_meta_key(job_id)
    redis_client.persist(key)
    assert redis_client.ttl(key) == -1

    redis_store.assemble_rows(job_id, n_chunks=1)

    assert redis_client.ttl(key) > 0, "assemble_rows left the meta key untagged"


def test_write_chunk_carries_a_ttl(redis_client, job_id):
    # A chunk of a job that never closes is otherwise never deleted, and
    # nothing else would ever expire it.
    redis_store.write_chunk(job_id, 0, [{"index": 0}])
    assert redis_client.ttl(redis_store.job_chunk_key(job_id, 0)) > 0


def test_read_rows_paginates(redis_client, job_id):
    redis_store.create_job(job_id, total=5, fmt="smiles_list", client_ip="::1")
    redis_store.write_chunk(job_id, 0, [{"index": i} for i in range(5)])
    redis_store.assemble_rows(job_id, n_chunks=1)

    page = redis_store.read_rows(job_id, offset=2, limit=2)
    assert [r["index"] for r in page] == [2, 3]


def test_iter_all_rows_yields_every_row_in_order(redis_client, job_id):
    redis_store.create_job(job_id, total=7, fmt="smiles_list", client_ip="::1")
    redis_store.write_chunk(job_id, 0, [{"index": i} for i in range(7)])
    redis_store.assemble_rows(job_id, n_chunks=1)

    assert [r["index"] for r in redis_store.iter_all_rows(job_id, page=3)] == list(
        range(7)
    )


def test_a_missing_chunk_is_reported_not_swallowed(redis_client, job_id, caplog):
    # spec section 10: a job never completes silently wrong. If a chunk key
    # expired or was never written, the row count must come back short AND
    # the loss must be logged -- finalize_job turns that into a failed job.
    redis_store.create_job(job_id, total=4, fmt="smiles_list", client_ip="::1")
    redis_store.write_chunk(job_id, 0, [{"index": 0}, {"index": 1}])
    # chunk 1 deliberately never written

    with caplog.at_level("ERROR"):
        written = redis_store.assemble_rows(job_id, n_chunks=2)

    assert written == 2
    assert "INCOMPLETE" in caplog.text
    assert "[1]" in caplog.text


def test_assemble_rows_tolerates_a_zero_chunk_job(redis_client, job_id):
    # Redis rejects DEL with no keys. Reachable only through a caller bug,
    # but raising here would lose rows already assembled.
    redis_store.create_job(job_id, total=0, fmt="smiles_list", client_ip="::1")
    assert redis_store.assemble_rows(job_id, n_chunks=0) == 0


def test_a_progress_write_retags_a_meta_key_that_lost_its_ttl(redis_client, job_id):
    # HINCRBY/HSET recreate a missing hash with NO expiry. Under volatile-lru
    # the meta key is an eviction candidate at any time, so this is not a
    # once-per-24h edge case -- and if the job never reaches assemble_rows
    # (worker dies, chord never completes) nothing else would ever re-tag it.
    redis_store.create_job(job_id, total=10, fmt="smiles_list", client_ip="::1")
    key = redis_store.job_meta_key(job_id)

    redis_client.persist(key)  # stand in for the recreated, untagged key
    assert redis_client.ttl(key) == -1
    redis_store.bump_job_done(job_id, index=0, done=1, failed=0)
    assert redis_client.ttl(key) > 0, "bump_job_done left the key untagged"

    redis_client.persist(key)
    assert redis_client.ttl(key) == -1
    redis_store.set_job_status(job_id, "running")
    assert redis_client.ttl(key) > 0, "set_job_status left the key untagged"


def test_a_progress_write_does_not_extend_a_live_ttl(redis_client, job_id):
    # EXPIRE NX, not EXPIRE. Re-arming the full 24h on every progress bump
    # would push a busy job's real expiry past the `expires` timestamp
    # create_job recorded and the API reports as expires_at.
    redis_store.create_job(job_id, total=10, fmt="smiles_list", client_ip="::1")
    key = redis_store.job_meta_key(job_id)
    redis_client.expire(key, 50)

    redis_store.bump_job_done(job_id, index=0, done=1, failed=0)
    redis_store.set_job_status(job_id, "running")

    assert 0 < redis_client.ttl(key) <= 50


def test_begin_chunk_refuses_an_already_terminal_job(redis_client, job_id):
    # I1: a chunk redelivered AFTER the job closed must not reopen it --
    # the chord body has already fired once and will not fire again, so
    # nothing would ever close it a second time.
    redis_store.create_job(job_id, total=1, fmt="smiles_list", client_ip="::1")
    redis_store.set_job_status(job_id, "done")

    assert redis_store.begin_chunk(job_id) is False
    assert redis_store.read_job_meta(job_id)["status"] == "done"


def test_begin_chunk_also_refuses_a_failed_job(redis_client, job_id):
    redis_store.create_job(job_id, total=1, fmt="smiles_list", client_ip="::1")
    redis_store.set_job_status(job_id, "failed")

    assert redis_store.begin_chunk(job_id) is False
    assert redis_store.read_job_meta(job_id)["status"] == "failed"


def test_begin_chunk_admits_a_non_terminal_job_and_marks_it_running(
    redis_client, job_id
):
    redis_store.create_job(job_id, total=1, fmt="smiles_list", client_ip="::1")

    assert redis_store.begin_chunk(job_id) is True
    assert redis_store.read_job_meta(job_id)["status"] == "running"


def test_begin_chunk_retags_a_meta_key_that_lost_its_ttl(redis_client, job_id):
    redis_store.create_job(job_id, total=1, fmt="smiles_list", client_ip="::1")
    key = redis_store.job_meta_key(job_id)
    redis_client.persist(key)
    assert redis_client.ttl(key) == -1

    assert redis_store.begin_chunk(job_id) is True

    assert redis_client.ttl(key) > 0, "begin_chunk left the key untagged"


def test_begin_chunk_does_not_extend_a_live_ttl(redis_client, job_id):
    # Same NX rule as the progress writes: re-arming the full window on every
    # chunk would push the real expiry past the advertised expires_at.
    redis_store.create_job(job_id, total=1, fmt="smiles_list", client_ip="::1")
    key = redis_store.job_meta_key(job_id)
    redis_client.expire(key, 50)

    redis_store.begin_chunk(job_id)

    assert 0 < redis_client.ttl(key) <= 50


def test_bump_job_done_is_idempotent_per_chunk(redis_client, job_id):
    # I1: a redelivered chunk (task_acks_late=True makes this real) must
    # not double-count molecules the first delivery already counted.
    redis_store.create_job(job_id, total=4, fmt="smiles_list", client_ip="::1")

    redis_store.bump_job_done(job_id, index=0, done=2, failed=0)
    redis_store.bump_job_done(job_id, index=0, done=2, failed=0)  # redelivered
    meta = redis_store.read_job_meta(job_id)
    assert meta["done"] == "2", "the same chunk index was counted twice"

    redis_store.bump_job_done(job_id, index=1, done=2, failed=0)
    meta = redis_store.read_job_meta(job_id)
    assert meta["done"] == "4", "a genuinely different chunk was not counted"


def test_worker_opsin_status_round_trips(redis_client):
    # Clear first, for the same reason its `is False` sibling below does
    # (TEST-1). The autouse pretend_a_worker_has_opsin fixture in conftest
    # writes a healthy pid before every test, so without this delete the
    # `is True` assertion is satisfied by the FIXTURE, not by the write under
    # test -- mutation showed 3 of the 4 tests for this function still passed
    # with record_worker_opsin_status neutered.
    redis_client.delete("orthonym:workers:opsin")

    redis_store.record_worker_opsin_status(999001, ok=True)
    try:
        assert redis_store.any_worker_has_opsin() is True
        assert redis_client.hget("orthonym:workers:opsin", "999001") is not None, (
            "any_worker_has_opsin() said yes but this pid's field is absent, "
            "so something else answered for it"
        )
    finally:
        redis_client.hdel("orthonym:workers:opsin", "999001")


def test_a_failed_worker_does_not_count_as_having_opsin(redis_client):
    # Clear first: this asserts on a global property ("is ANY worker
    # healthy"), so a stray ok field from another test -- or from a later
    # task's autouse fixture -- would mask the thing being tested. Round 3
    # review, finding 3: worker status moved from one key per pid
    # ("orthonym:worker:{pid}:opsin", scan_iter-discovered) to a single hash
    # ("orthonym:workers:opsin", field = pid) so any_worker_has_opsin() never
    # scans the keyspace.
    redis_client.delete("orthonym:workers:opsin")

    redis_store.record_worker_opsin_status(999002, ok=False)
    try:
        # Call the function the test is named after. Asserting only that the
        # string "failed" was written somewhere would not catch
        # any_worker_has_opsin() treating any status at all as healthy --
        # and that function is what makes /api/health honest and what
        # decides whether naming is served at all.
        assert redis_store.any_worker_has_opsin() is False
        # ...and the failure status was actually RECORDED (TEST-2). An empty
        # hash satisfies `is False` identically, so without this the test
        # cannot tell "the writer correctly stored a failure" from "the
        # writer dropped failure statuses on the floor" -- and the second is
        # a worker that silently never reports its own breakage.
        assert redis_client.hget("orthonym:workers:opsin", "999002") is not None, (
            "the failure status was never written; any_worker_has_opsin() "
            "returned False only because the hash is empty"
        )
    finally:
        redis_client.hdel("orthonym:workers:opsin", "999002")


def test_record_worker_opsin_status_prunes_stale_entries_on_write(
    redis_client, monkeypatch
):
    # Round 3 review, finding 3: the hash must not grow forever across
    # worker restarts -- pruning happens on every write, not just on read.
    import time

    monkeypatch.setattr(redis_store, "_WORKER_STATUS_TTL", 1, raising=False)
    redis_client.hset(
        "orthonym:workers:opsin", "999003", f"ok:{int(time.time()) - 10}"
    )
    try:
        # A live sibling written by another worker must survive this write;
        # only aged-out entries go.
        redis_client.hset("orthonym:workers:opsin", "999006", f"ok:{int(time.time())}")
        redis_store.record_worker_opsin_status(999004, ok=True)
        assert redis_client.hget("orthonym:workers:opsin", "999003") is None
        assert redis_client.hget("orthonym:workers:opsin", "999004") is not None
        assert redis_client.hget("orthonym:workers:opsin", "999006") is not None
    finally:
        redis_client.hdel(
            "orthonym:workers:opsin", "999003", "999004", "999006"
        )


def test_any_worker_has_opsin_ignores_an_aged_out_entry(
    redis_client, monkeypatch
):
    # A dead worker's "ok" must not linger past _WORKER_STATUS_TTL and make
    # health lie -- covers the read side; the write-side prune above covers
    # the other half of the same guarantee.
    import time

    redis_client.delete("orthonym:workers:opsin")
    monkeypatch.setattr(redis_store, "_WORKER_STATUS_TTL", 1, raising=False)
    redis_client.hset(
        "orthonym:workers:opsin", "999005", f"ok:{int(time.time()) - 10}"
    )
    try:
        assert redis_store.any_worker_has_opsin() is False
    finally:
        redis_client.hdel("orthonym:workers:opsin", "999005")


def test_a_malformed_worker_entry_is_not_health_and_is_pruned(redis_client):
    # A value that is not "<status>:<unix ts>" must never count as a healthy
    # worker, must not make the health check raise, and must not sit in the
    # hash for good.
    redis_client.delete("orthonym:workers:opsin")
    redis_client.hset("orthonym:workers:opsin", "999007", "garbage")
    try:
        assert redis_store.any_worker_has_opsin() is False
        redis_store.record_worker_opsin_status(999008, ok=True)
        assert redis_client.hget("orthonym:workers:opsin", "999007") is None
    finally:
        redis_client.hdel("orthonym:workers:opsin", "999007", "999008")


def test_closing_a_job_does_not_push_its_expiry_past_what_it_promised(redis_client):
    """deferred-3: assemble_rows re-armed the meta key with a PLAIN EXPIRE,
    while _retag_if_untagged and the begin_chunk Lua both use NX for exactly
    this reason.

    create_job records an absolute `expires` field, and GET /api/jobs/{id}
    reports it as expires_at. A plain EXPIRE at close restarts the full 24
    hours from the moment the job finished, so the real expiry drifts past
    the advertised one by roughly the job's runtime -- on a long batch, hours.

    The elapsed time has to be simulated for the drift to be visible at all.
    A first draft of this test created and closed the job in the same second,
    where `now + TTL` and `created + TTL` are equal by construction and the
    assertion passed with the bug still in place. Ageing the job by an hour
    is what makes the two branches distinguishable.

    It errs safe (data lives longer than promised, never shorter), which is
    why it was deferred. Fixed anyway because leaving one half of an
    NX/non-NX pair inconsistent inside a single file is how this bug class
    comes back.
    """
    job_id = "job-ttl-drift-probe"
    redis_store.create_job(job_id, total=1, fmt="smiles_list", client_ip="203.0.113.9")
    meta_key = redis_store.job_meta_key(job_id)
    try:
        aged_by = 3600  # pretend the job was submitted an hour ago
        promised = int(redis_client.hget(meta_key, "expires")) - aged_by
        redis_client.hset(meta_key, "expires", promised)
        redis_client.expire(meta_key, redis_client.ttl(meta_key) - aged_by)

        redis_store.write_chunk(job_id, 0, [{"index": 0, "input": "CCO", "status": "pin"}])
        redis_store.assemble_rows(job_id, n_chunks=1)

        actual_expiry = int(time.time()) + redis_client.ttl(meta_key)
        assert actual_expiry <= promised + 5, (
            f"the key now expires {actual_expiry - promised}s after the "
            "expires_at the API already reported to the caller"
        )
    finally:
        redis_client.delete(meta_key, redis_store.job_rows_key(job_id))
