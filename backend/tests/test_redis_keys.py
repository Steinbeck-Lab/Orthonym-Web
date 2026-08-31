from app import redis_store


def test_keys_are_namespaced_and_stable():
    assert redis_store.job_meta_key("abc") == "stitch:job:abc:meta"
    assert redis_store.job_rows_key("abc") == "stitch:job:abc:rows"
    assert redis_store.job_chunk_key("abc", 3) == "stitch:job:abc:chunk:3"


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
    redis_store.create_job(job_id, total=10, fmt="smiles_list", client_ip="::1")
    redis_store.bump_job_done(job_id, done=4, failed=1)
    redis_store.bump_job_done(job_id, done=3, failed=0)
    meta = redis_store.read_job_meta(job_id)
    assert meta["done"] == "7"
    assert meta["failed"] == "1"


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


def test_assembled_rows_and_meta_both_carry_a_ttl(redis_client, job_id):
    redis_store.create_job(job_id, total=1, fmt="smiles_list", client_ip="::1")
    redis_store.write_chunk(job_id, 0, [{"index": 0}])
    redis_store.assemble_rows(job_id, n_chunks=1)

    # A job that never expires would grow Redis without bound, and the
    # no-database rule depends on results being transient.
    assert redis_client.ttl(redis_store.job_rows_key(job_id)) > 0
    assert redis_client.ttl(redis_store.job_meta_key(job_id)) > 0


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
    redis_store.bump_job_done(job_id, done=1, failed=0)
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

    redis_store.bump_job_done(job_id, done=1, failed=0)
    redis_store.set_job_status(job_id, "running")

    assert 0 < redis_client.ttl(key) <= 50


def test_worker_opsin_status_round_trips(redis_client):
    redis_store.record_worker_opsin_status(999001, ok=True)
    try:
        assert redis_store.any_worker_has_opsin() is True
    finally:
        redis_client.hdel("stitch:workers:opsin", "999001")


def test_a_failed_worker_does_not_count_as_having_opsin(redis_client):
    # Clear first: this asserts on a global property ("is ANY worker
    # healthy"), so a stray ok field from another test -- or from a later
    # task's autouse fixture -- would mask the thing being tested. Round 3
    # review, finding 3: worker status moved from one key per pid
    # ("stitch:worker:{pid}:opsin", scan_iter-discovered) to a single hash
    # ("stitch:workers:opsin", field = pid) so any_worker_has_opsin() never
    # scans the keyspace.
    redis_client.delete("stitch:workers:opsin")

    redis_store.record_worker_opsin_status(999002, ok=False)
    try:
        # Call the function the test is named after. Asserting only that the
        # string "failed" was written somewhere would not catch
        # any_worker_has_opsin() treating any status at all as healthy --
        # and that function is what makes /api/health honest and what
        # decides whether naming is served at all.
        assert redis_store.any_worker_has_opsin() is False
    finally:
        redis_client.hdel("stitch:workers:opsin", "999002")


def test_record_worker_opsin_status_prunes_stale_entries_on_write(
    redis_client, monkeypatch
):
    # Round 3 review, finding 3: the hash must not grow forever across
    # worker restarts -- pruning happens on every write, not just on read.
    import time

    monkeypatch.setattr(redis_store, "_WORKER_STATUS_TTL", 1, raising=False)
    redis_client.hset(
        "stitch:workers:opsin", "999003", f"ok:{int(time.time()) - 10}"
    )
    try:
        redis_store.record_worker_opsin_status(999004, ok=True)
        assert redis_client.hget("stitch:workers:opsin", "999003") is None
        assert redis_client.hget("stitch:workers:opsin", "999004") is not None
    finally:
        redis_client.hdel("stitch:workers:opsin", "999003", "999004")


def test_any_worker_has_opsin_ignores_an_aged_out_entry(
    redis_client, monkeypatch
):
    # A dead worker's "ok" must not linger past _WORKER_STATUS_TTL and make
    # health lie -- covers the read side; the write-side prune above covers
    # the other half of the same guarantee.
    import time

    redis_client.delete("stitch:workers:opsin")
    monkeypatch.setattr(redis_store, "_WORKER_STATUS_TTL", 1, raising=False)
    redis_client.hset(
        "stitch:workers:opsin", "999005", f"ok:{int(time.time()) - 10}"
    )
    try:
        assert redis_store.any_worker_has_opsin() is False
    finally:
        redis_client.hdel("stitch:workers:opsin", "999005")
