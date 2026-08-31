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


def test_worker_opsin_status_round_trips(redis_client):
    redis_store.record_worker_opsin_status(999001, ok=True)
    try:
        assert redis_store.any_worker_has_opsin() is True
    finally:
        redis_client.delete("orthonym:worker:999001:opsin")


def test_a_failed_worker_does_not_count_as_having_opsin(redis_client):
    redis_store.record_worker_opsin_status(999002, ok=False)
    try:
        keys = list(redis_client.scan_iter(match="orthonym:worker:*:opsin"))
        statuses = {redis_client.get(k) for k in keys}
        assert "failed" in statuses
    finally:
        redis_client.delete("orthonym:worker:999002:opsin")
