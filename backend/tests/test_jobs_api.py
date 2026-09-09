"""Job endpoints, driven with Celery in eager mode.

Eager mode runs tasks inline, so this exercises the real task bodies, the
real Redis writes and the real assembly ordering without needing a worker
process. The forked-worker JVM behaviour is covered separately in
test_celery_jvm_fork.py -- that is the one thing eager mode cannot test.
"""

import pytest
from fastapi.testclient import TestClient

from app import jobs_api, redis_store, tasks
from app.celery_app import celery_app
from app.core.config import get_settings
from app.inputs import ParsedMolecule
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def eager_celery():
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    yield
    celery_app.conf.task_always_eager = False


def _submit(text: str) -> dict:
    response = client.post("/api/jobs", json={"text": text})
    assert response.status_code == 200, response.text
    return response.json()


def test_parse_preview_counts_without_queueing():
    response = client.post(
        "/api/parse-preview", json={"text": "CCO\nc1ccccc1\nCCC\n"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["format"] == "smiles_list"
    assert body["molecule_count"] == 3
    assert len(body["sample"]) == 3


def test_parse_preview_caps_the_sample_at_five():
    text = "\n".join(["CCO"] * 20)
    body = client.post("/api/parse-preview", json={"text": text}).json()
    assert body["molecule_count"] == 20
    assert len(body["sample"]) == 5


def test_parse_preview_reports_bad_records_without_failing():
    body = client.post(
        "/api/parse-preview", json={"text": "CCO\nnot_a_smiles(((\n"}
    ).json()
    assert body["molecule_count"] == 2
    assert body["errors"]


def test_submit_then_poll_then_read_results(redis_client):
    submitted = _submit("CCO\nc1ccccc1\n")
    job_id = submitted["job_id"]
    assert submitted["molecule_count"] == 2

    status = client.get(f"/api/jobs/{job_id}").json()
    assert status["status"] == "done"
    assert status["total"] == 2
    assert status["done"] == 2

    results = client.get(f"/api/jobs/{job_id}/results").json()
    assert [r["index"] for r in results["rows"]] == [0, 1]
    assert results["rows"][0]["name"] == "ethanol"
    assert results["rows"][0]["status"] == "pin"
    # A batch row must never carry a picture.
    assert "depiction_svg" not in results["rows"][0]


def test_results_are_paginated(redis_client):
    job_id = _submit("\n".join(["CCO", "CCC", "CCCC", "c1ccccc1"]))["job_id"]
    page = client.get(
        f"/api/jobs/{job_id}/results", params={"offset": 1, "limit": 2}
    ).json()
    assert [r["index"] for r in page["rows"]] == [1, 2]
    assert page["total"] == 4


def _rows_with_tiers(job_id, rows):
    """Overwrite a submitted job's assembled rows with hand-built ones.

    The engine will not produce a chosen spread of tiers on demand, and the
    sort has to be exercised against a spread. Everything else about the job
    -- meta, counts, TTL -- is real.
    """
    redis_client_rows = redis_store.job_rows_key(job_id)
    redis_store.get_redis().delete(redis_client_rows)
    redis_store.write_chunk(job_id, 0, rows)
    redis_store.assemble_rows(job_id, n_chunks=1)


def test_results_sort_orders_the_whole_job_not_just_one_page(redis_client):
    # The point of the feature: a sorted page must be a page of the SORTED
    # JOB. Sorting a 50-row slice would only reorder rows the client already
    # had, and the ask was to bring every abstain onto one screen.
    job_id = _submit("\n".join(["CCO"] * 6))["job_id"]
    _rows_with_tiers(
        job_id,
        [
            {"index": 0, "input": "a", "status": "pin", "name": "a"},
            {"index": 1, "input": "b", "status": "abstain"},
            {"index": 2, "input": "c", "status": "pin", "name": "c"},
            {"index": 3, "input": "d", "status": "error"},
            {"index": 4, "input": "e", "status": "fallback", "name": "e"},
            {"index": 5, "input": "f", "status": "abstain"},
        ],
    )

    # Page 2 of a tier sort must carry rows that page 1 pushed off the end --
    # rows 3 and 5 here, which an unsorted page 2 would never contain.
    first = client.get(
        f"/api/jobs/{job_id}/results",
        params={"offset": 0, "limit": 3, "sort": "tier"},
    ).json()
    second = client.get(
        f"/api/jobs/{job_id}/results",
        params={"offset": 3, "limit": 3, "sort": "tier"},
    ).json()

    assert [r["index"] for r in first["rows"]] == [0, 2, 4]
    assert [r["index"] for r in second["rows"]] == [1, 5, 3]
    # Every row exactly once across the two pages.
    assert sorted(r["index"] for r in first["rows"] + second["rows"]) == [0, 1, 2, 3, 4, 5]


def test_results_sort_descending_reverses_only_the_sort_key(redis_client):
    job_id = _submit("\n".join(["CCO"] * 4))["job_id"]
    _rows_with_tiers(
        job_id,
        [
            {"index": 0, "input": "a", "status": "pin", "name": "a"},
            {"index": 1, "input": "b", "status": "pin", "name": "b"},
            {"index": 2, "input": "c", "status": "abstain"},
            {"index": 3, "input": "d", "status": "abstain"},
        ],
    )
    rows = client.get(
        f"/api/jobs/{job_id}/results",
        params={"limit": 10, "sort": "tier", "order": "desc"},
    ).json()["rows"]
    # Abstains first, but 2 before 3: within a tier the submission order is
    # preserved in BOTH directions.
    assert [r["index"] for r in rows] == [2, 3, 0, 1]


def test_the_default_results_order_is_untouched(redis_client):
    # The fast path. `sort=index&order=asc` must stay a single slice of the
    # stored list -- no full decode -- so the common case cannot regress.
    job_id = _submit("\n".join(["CCO", "CCC", "CCCC", "c1ccccc1"]))["job_id"]
    plain = client.get(f"/api/jobs/{job_id}/results", params={"limit": 10}).json()
    explicit = client.get(
        f"/api/jobs/{job_id}/results",
        params={"limit": 10, "sort": "index", "order": "asc"},
    ).json()
    assert [r["index"] for r in plain["rows"]] == [0, 1, 2, 3]
    assert plain["rows"] == explicit["rows"]


def test_an_unknown_sort_field_is_a_422_not_a_silent_no_op(redis_client):
    job_id = _submit("\n".join(["CCO", "CCC"]))["job_id"]
    response = client.get(
        f"/api/jobs/{job_id}/results", params={"sort": "smiles"}
    )
    assert response.status_code == 422, response.text


def test_chunk_order_is_preserved_across_multiple_chunks(redis_client, monkeypatch):
    from app.core.config import get_settings

    settings = get_settings()
    # BOTH knobs, and the first one is the point: with FAST_PATH_MAX_MOLECULES
    # at its default 10, a 5-molecule job takes the single-task fast path and
    # never chunks at all -- so this test would pass while exercising none of
    # the chunking, chord or assembly-ordering code it is named for.
    monkeypatch.setattr(settings, "FAST_PATH_MAX_MOLECULES", 1)
    monkeypatch.setattr(settings, "BATCH_CHUNK_SIZE", 2)

    smiles = ["CCO", "CCC", "CCCC", "CCCCC", "c1ccccc1"]
    job_id = _submit("\n".join(smiles))["job_id"]
    rows = client.get(
        f"/api/jobs/{job_id}/results", params={"limit": 100}
    ).json()["rows"]
    # Assert the job GENUINELY chunked before asserting on the order (TEST-3).
    # Both knobs are monkeypatched above, but nothing checked they took
    # effect: if either were ever reverted the job would take the single-task
    # fast path, produce five correctly-ordered rows anyway, and this test
    # would keep passing while exercising none of the chunking, chord or
    # assembly-ordering code it is named for. That exact mistake shipped here
    # once already.
    expected_chunks = -(-len(smiles) // settings.BATCH_CHUNK_SIZE)  # ceil
    assert expected_chunks > 1, "the fixture no longer produces multiple chunks"
    assert settings.FAST_PATH_MAX_MOLECULES < len(smiles), (
        "this job would take the single-task fast path and never chunk"
    )
    assert [r["index"] for r in rows] == [0, 1, 2, 3, 4]
    assert [r["input"] for r in rows] == smiles


def test_dispatch_batch_chunks_and_assembles_in_order(redis_client, job_id):
    """The chunking path directly: 5 molecules at chunk size 2 is 3 chunks.

    Ordering across chunks and the chunk count are what this covers. It does
    NOT prove rows take their index from the data rather than from
    arithmetic -- with contiguous zero-based indices the two agree by
    construction, so that property needs the next test.
    """
    from app import redis_store
    from app.inputs import ParsedMolecule
    from app.jobs_api import prepared_payload
    from app.tasks import dispatch_batch

    smiles = ["CCO", "CCC", "CCCC", "CCCCC", "c1ccccc1"]
    molecules = [
        ParsedMolecule(index=i, raw_input=s, input_id=None, smiles=s, error=None)
        for i, s in enumerate(smiles)
    ]
    redis_store.create_job(job_id, total=5, fmt="smiles_list", client_ip="::1")

    assert dispatch_batch(job_id, prepared_payload(molecules), True, 2) == 3

    rows = redis_store.read_rows(job_id, 0, 100)
    assert [r["index"] for r in rows] == [0, 1, 2, 3, 4]
    assert [r["input"] for r in rows] == smiles
    assert redis_store.read_job_meta(job_id)["status"] == "done"


def test_row_indices_come_from_the_data_not_the_chunk_position(redis_client, job_id):
    """Non-contiguous indices, which arithmetic cannot reproduce.

    prepared_payload normally emits index == position, so
    prepared[0]["index"] and index * chunk_size agree and a contiguous
    fixture cannot tell them apart. These molecules are numbered 10..14, so
    a row numbered from the chunk's position would come back 0..4.
    """
    from app import redis_store
    from app.tasks import dispatch_batch

    prepared = [
        {
            "index": 10 + i,
            "raw_input": s,
            "input_id": None,
            "smiles": s,
            "error": None,
        }
        for i, s in enumerate(["CCO", "CCC", "CCCC", "CCCCC", "c1ccccc1"])
    ]
    redis_store.create_job(job_id, total=5, fmt="smiles_list", client_ip="::1")

    assert dispatch_batch(job_id, prepared, True, 2) == 3

    rows = redis_store.read_rows(job_id, 0, 100)
    assert [r["index"] for r in rows] == [10, 11, 12, 13, 14]


def test_a_soft_time_limit_keeps_named_rows_and_times_out_the_rest(
    redis_client, job_id, monkeypatch
):
    """The timeout path, which nothing covered before.

    SoftTimeLimitExceeded subclasses Exception, so the per-molecule
    `except Exception` used to swallow it: the timeout became one misleading
    "Naming failed" row and the loop ran on past the limit. This raises it
    from the third molecule and asserts the first two survive as real rows
    while the rest are marked limit_code="timeout".
    """
    from celery.exceptions import SoftTimeLimitExceeded

    from app import redis_store, tasks

    calls = {"n": 0}
    real = tasks.name_one

    def fake_name_one(smiles, best_effort, verify=True):
        calls["n"] += 1
        if calls["n"] > 2:
            raise SoftTimeLimitExceeded()
        return real(smiles, best_effort)

    monkeypatch.setattr(tasks, "name_one", fake_name_one)

    smiles = ["CCO", "CCC", "CCCC", "CCCCC"]
    prepared = [
        {"index": i, "raw_input": s, "input_id": None, "smiles": s, "error": None}
        for i, s in enumerate(smiles)
    ]
    redis_store.create_job(job_id, total=4, fmt="smiles_list", client_ip="::1")
    tasks.run_chunk(job_id, 0, prepared, True)
    redis_store.assemble_rows(job_id, n_chunks=1)

    rows = redis_store.read_rows(job_id, 0, 100)
    assert len(rows) == 4, "the timeout lost rows instead of marking them"
    assert rows[0]["status"] == "pin"
    assert [r["limit_code"] for r in rows[2:]] == ["timeout", "timeout"]


def test_one_molecule_raising_does_not_lose_the_rest_of_the_chunk(
    redis_client, job_id, monkeypatch
):
    """The "one bad molecule must not lose the other 24" constraint.

    The existing coverage exercises a PARSE failure, which is a different
    branch -- this one makes naming itself raise.
    """
    from app import redis_store, tasks

    real = tasks.name_one

    def fake_name_one(smiles, best_effort, verify=True):
        if smiles == "CCC":
            raise RuntimeError("engine exploded")
        return real(smiles, best_effort)

    monkeypatch.setattr(tasks, "name_one", fake_name_one)

    prepared = [
        {"index": i, "raw_input": s, "input_id": None, "smiles": s, "error": None}
        for i, s in enumerate(["CCO", "CCC", "CCCC"])
    ]
    redis_store.create_job(job_id, total=3, fmt="smiles_list", client_ip="::1")
    tasks.run_chunk(job_id, 0, prepared, True)
    redis_store.assemble_rows(job_id, n_chunks=1)

    rows = redis_store.read_rows(job_id, 0, 100)
    assert [r["status"] for r in rows] == ["pin", "error", "pin"]
    assert "engine exploded" in rows[1]["error"]


def test_a_redelivered_chunk_does_not_uncomplete_a_finished_job(
    redis_client, job_id
):
    """I1: task_acks_late=True makes chunk redelivery real. A redelivered
    chunk must not flip a finished job back to "running" (the chord body
    has already fired once and will not fire again, so nothing would ever
    close it a second time) or double-count its molecules past `total`.
    """
    from app import redis_store
    from app.tasks import dispatch_batch, run_chunk

    smiles = ["CCO", "CCC"]
    prepared = [
        {"index": i, "raw_input": s, "input_id": None, "smiles": s, "error": None}
        for i, s in enumerate(smiles)
    ]
    redis_store.create_job(job_id, total=2, fmt="smiles_list", client_ip="::1")
    assert dispatch_batch(job_id, prepared, True, 2) == 1  # one chunk

    meta = redis_store.read_job_meta(job_id)
    assert meta["status"] == "done"
    assert meta["done"] == "2"

    # Redeliver: run_chunk fires again for the SAME chunk, exactly as
    # task_acks_late would after a lost ack post-completion.
    result = run_chunk(job_id, 0, prepared, True)

    meta_after = redis_store.read_job_meta(job_id)
    assert result == 0, "the redelivered chunk should short-circuit, not re-run"
    assert meta_after["status"] == "done", "redelivery flipped a done job back"
    assert int(meta_after["done"]) <= int(meta_after["total"])


def test_a_redelivered_fast_path_task_does_not_uncomplete_a_finished_job(
    redis_client, job_id, monkeypatch
):
    """I1, concern raised on translate_job_inline specifically: this task
    had the identical unconditional set_job_status(job_id, "running")
    run_chunk had, on the DEFAULT path for every job at or under
    FAST_PATH_MAX_MOLECULES. "It self-heals via _close_job at its own
    end" only holds for a redelivery that actually reaches its own end --
    one that crashes between the status flip and write_chunk (an OOM
    kill, a hard-time-limit SIGKILL, a Redis blip) would leave an
    already-done job stuck at "running" forever, because assemble_rows
    already deleted the only chunk key on the first, successful close, so
    there is nothing left to rebuild from and _close_job never runs on
    the crashed attempt.

    A test that just calls the whole function twice and checks the FINAL
    state would pass via that self-heal even without the fix -- verified
    empirically while writing this: the unguarded code, run to completion
    twice with no interruption, always ends up back at "done" with
    correct rows, because write_chunk unconditionally recreates the
    (deleted) chunk key before _close_job ever looks for it. That is
    exactly the "test does not test its name" shape this branch has hit
    before, so this asserts on the MECHANISM instead: write_chunk must
    never be re-entered at all for an already-done job. The chunk key is
    also deleted explicitly first, the way assemble_rows already does on
    a real close, to make explicit that nothing is left to rebuild from.
    """
    from app import redis_store, tasks

    prepared = [
        {
            "index": i,
            "raw_input": s,
            "input_id": None,
            "smiles": s,
            "error": None,
        }
        for i, s in enumerate(["CCO", "CCC"])
    ]
    redis_store.create_job(job_id, total=2, fmt="smiles_list", client_ip="::1")

    real_write_chunk = redis_store.write_chunk
    calls = {"n": 0}

    def _counting_write_chunk(*args, **kwargs):
        calls["n"] += 1
        return real_write_chunk(*args, **kwargs)

    monkeypatch.setattr(tasks.redis_store, "write_chunk", _counting_write_chunk)

    first = tasks.translate_job_inline(job_id, prepared, True)
    assert calls["n"] == 1, "setup failed: the first run did not write a chunk"
    meta = redis_store.read_job_meta(job_id)
    assert meta["status"] == "done"

    # assemble_rows already deleted chunk 0 as part of the first close;
    # delete it again explicitly so nothing here relies on that
    # implementation detail holding.
    redis_client.delete(redis_store.job_chunk_key(job_id, 0))

    # Redeliver: the same task fires again, exactly as task_acks_late
    # would after a lost ack on an attempt that had already completed.
    second = tasks.translate_job_inline(job_id, prepared, True)

    assert calls["n"] == 1, (
        "the redelivered call re-entered write_chunk instead of being "
        "refused by begin_chunk -- this is exactly the window a crash "
        "would leave the job stuck at 'running' in, forever"
    )
    meta_after = redis_store.read_job_meta(job_id)
    assert meta_after["status"] == "done", "redelivery flipped a done job back"
    assert second == first, (
        "the redelivered call did not return the job's real, existing rows"
    )


def test_a_redelivered_close_does_not_destroy_a_finished_job(redis_client):
    """finalize_job must be idempotent.

    task_acks_late=True makes redelivery real, and assemble_rows deletes the
    chunk keys as it goes -- so a second, naive close would find nothing,
    wipe the rows and flip a done job to failed.
    """
    from app.tasks import finalize_job

    job_id = _submit("CCO\nc1ccccc1\n")["job_id"]
    before = client.get(f"/api/jobs/{job_id}/results").json()
    assert before["rows"], "setup failed: no rows to protect"

    finalize_job(None, job_id, 1)

    after = client.get(f"/api/jobs/{job_id}").json()
    assert after["status"] == "done"
    assert client.get(f"/api/jobs/{job_id}/results").json()["rows"] == before["rows"]


def test_a_close_with_missing_meta_does_not_claim_done(redis_client):
    """A job whose meta was evicted must not be reported complete.

    Reading `total` as 0 would make `written < total` false and set "done"
    over any row count; writing a status at all would recreate the hash with
    only that field, and a later read would then 500 instead of 410.
    """
    from app import redis_store
    from app.tasks import finalize_job

    job_id = _submit("CCO\n")["job_id"]
    redis_store.get_redis().delete(redis_store.job_meta_key(job_id))

    assert finalize_job(None, job_id, 1) == 0
    assert redis_store.read_job_meta(job_id) is None, (
        "close resurrected a partial meta hash; /api/jobs/{id} will now 500"
    )
    assert client.get(f"/api/jobs/{job_id}").status_code == 410


def test_csv_is_refused_while_a_job_is_still_running(redis_client, job_id):
    # The CSV is the artefact users keep. A mid-run download would be a
    # header-only or half-length file, byte-indistinguishable from a
    # complete one.
    from app import redis_store

    redis_store.create_job(job_id, total=5, fmt="smiles_list", client_ip="::1")
    redis_store.set_job_status(job_id, "running")
    response = client.get(f"/api/jobs/{job_id}/results.csv")
    assert response.status_code == 409
    assert "running" in response.json()["detail"]


def test_a_failed_jobs_csv_is_served_but_labelled(redis_client, job_id):
    # Partial rows are real results, so they are served -- but the header and
    # the filename must say the file is short.
    from app import redis_store

    redis_store.create_job(job_id, total=5, fmt="smiles_list", client_ip="::1")
    redis_store.write_chunk(job_id, 0, [{"index": 0, "input": "CCO"}])
    redis_store.assemble_rows(job_id, n_chunks=1)
    redis_store.set_job_status(job_id, "failed")

    response = client.get(f"/api/jobs/{job_id}/results.csv")
    assert response.status_code == 200
    assert response.headers["X-STITCH-Job-Status"] == "failed"
    assert "-partial.csv" in response.headers["content-disposition"]


def test_a_formula_leading_cell_is_neutralised_in_the_csv(redis_client, job_id):
    # `input` is verbatim user text. A pasted line opening with "=" becomes a
    # live formula when the file is opened in Excel or Sheets.
    from app import redis_store

    redis_store.create_job(job_id, total=1, fmt="smiles_list", client_ip="::1")
    redis_store.write_chunk(
        job_id, 0, [{"index": 0, "input": "=cmd|'/c calc'!A1", "status": "error"}]
    )
    redis_store.assemble_rows(job_id, n_chunks=1)
    redis_store.set_job_status(job_id, "done")

    body = client.get(f"/api/jobs/{job_id}/results.csv").text
    assert "'=cmd" in body, "formula-leading cell was not neutralised"


def test_retrievable_is_short_of_total_on_a_failed_job(redis_client, job_id):
    # `total` is what was submitted; `retrievable` is what can be paged. A
    # client paginating to `total` on a failed job would never terminate.
    from app import redis_store

    redis_store.create_job(job_id, total=5, fmt="smiles_list", client_ip="::1")
    # "status" is required by BatchRow -- /results validates rows against it
    # (unlike /results.csv, which writes raw dicts), so a fixture row missing
    # it would 500 with a pydantic ValidationError instead of exercising the
    # retrievable-vs-total assertion this test is actually about.
    redis_store.write_chunk(
        job_id, 0, [{"index": 0, "input": "CCO", "status": "pin"}]
    )
    redis_store.assemble_rows(job_id, n_chunks=1)
    redis_store.set_job_status(job_id, "failed")

    body = client.get(f"/api/jobs/{job_id}/results").json()
    assert body["total"] == 5
    assert body["retrievable"] == 1


def test_a_done_jobs_status_and_csv_stop_claiming_completeness_if_rows_are_evicted(
    redis_client,
):
    """C4: stitch:job:{id}:rows is TTL'd, and volatile-lru makes every
    TTL'd key an eviction candidate at any moment regardless of remaining
    TTL -- so a job can close honestly as "done" and still have its rows
    key evicted minutes later. Both read paths must catch that, not just
    /results (which already had `retrievable` to fall back on).
    """
    from app import redis_store

    job_id = _submit("CCO\nc1ccccc1\n")["job_id"]
    before = client.get(f"/api/jobs/{job_id}").json()
    assert before["status"] == "done"

    redis_store.get_redis().delete(redis_store.job_rows_key(job_id))

    status_after = client.get(f"/api/jobs/{job_id}").json()
    assert status_after["status"] == "failed", (
        "status endpoint kept claiming done over an empty result list"
    )

    csv_response = client.get(f"/api/jobs/{job_id}/results.csv")
    assert csv_response.status_code == 200
    assert csv_response.headers["X-STITCH-Job-Status"] == "failed"
    assert "-partial.csv" in csv_response.headers["content-disposition"]
    lines = [line for line in csv_response.text.splitlines() if line.strip()]
    assert len(lines) == 1, "CSV still served rows that no longer exist"


def test_a_preview_row_carries_no_tier(redis_client):
    # A preview row has no status: "the engine refused" and "nothing was
    # attempted" must not share the one field the product forbids conflating.
    body = client.post("/api/parse-preview", json={"text": "CCO\nbad(((\n"}).json()
    assert body["sample"]
    for row in body["sample"]:
        assert "status" not in row


def test_depict_rejects_an_absurdly_long_smiles():
    # MolFromSmiles and the draw call run synchronously in the web process
    # and RDKit does not release the GIL, so the input needs a bound.
    response = client.get("/api/depict", params={"smiles": "C" * 5000})
    assert response.status_code == 422


def test_depict_is_cacheable():
    # The results table calls this once per row, so a 1,000-row table is
    # 1,000 renders without a cache header.
    response = client.get("/api/depict", params={"smiles": "CCO"})
    assert "max-age" in response.headers.get("cache-control", "")


def test_a_json_body_without_text_is_400():
    # _read_input's three failure modes all used to surface as a raw 500:
    # a fileless multipart body (stream already consumed), an empty body,
    # and JSON missing "text".
    assert client.post("/api/jobs", json={}).status_code == 400


def test_an_empty_body_is_400():
    response = client.post(
        "/api/jobs", content=b"", headers={"content-type": "application/json"}
    )
    assert response.status_code == 400


def test_unparseable_molecule_becomes_an_error_row_not_a_failed_job(redis_client):
    job_id = _submit("CCO\nnot_a_smiles(((\n")["job_id"]
    status = client.get(f"/api/jobs/{job_id}").json()
    assert status["status"] == "done"
    assert status["failed"] == 1

    rows = client.get(f"/api/jobs/{job_id}/results").json()["rows"]
    assert rows[0]["status"] == "pin"
    assert rows[1]["status"] == "error"
    assert rows[1]["error"]


def test_a_job_missing_a_chunk_is_failed_not_done(redis_client, monkeypatch):
    # spec section 10 again, at the job level: an incomplete result list must
    # never be presented as a completed job.
    from app import redis_store

    job_id = _submit("CCO\nc1ccccc1\n")["job_id"]
    # A chunk key that is genuinely ABSENT, not present-and-empty: the
    # failure being modelled is a key that expired or was evicted between
    # the chunk task and assembly, and assemble_rows distinguishes the two.
    client_r = redis_store.get_redis()
    client_r.delete(redis_store.job_rows_key(job_id))
    client_r.delete(redis_store.job_chunk_key(job_id, 0))
    assert client_r.exists(redis_store.job_chunk_key(job_id, 0)) == 0
    from app.tasks import finalize_job

    finalize_job(None, job_id, 1)

    assert client.get(f"/api/jobs/{job_id}").json()["status"] == "failed"


def test_csv_download_has_a_header_and_one_line_per_molecule(redis_client):
    job_id = _submit("CCO\nc1ccccc1\n")["job_id"]
    response = client.get(f"/api/jobs/{job_id}/results.csv")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    lines = [line for line in response.text.splitlines() if line.strip()]
    assert lines[0].startswith("index,input,input_id,smiles,name,status")
    assert len(lines) == 3


def test_unknown_job_is_404():
    assert client.get("/api/jobs/no-such-job").status_code == 404


def test_expired_job_is_410(redis_client):
    job_id = _submit("CCO\n")["job_id"]
    # Simulate the TTL elapsing: the meta key is gone, the rows key is not.
    redis_client.delete(f"stitch:job:{job_id}:meta")
    try:
        assert client.get(f"/api/jobs/{job_id}").status_code == 410
    finally:
        redis_client.delete(f"stitch:job:{job_id}:rows")


def test_oversize_input_is_413(monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "MAX_BATCH_SIZE", 2)
    response = client.post("/api/jobs", json={"text": "CCO\nCCC\nCCCC\n"})
    assert response.status_code == 413
    assert "2" in response.json()["detail"]


def test_delete_removes_the_job(redis_client):
    envelope = _submit("CCO\n")
    job_id = envelope["job_id"]
    r = client.delete(
        f"/api/jobs/{job_id}", params={"owner_token": envelope["owner_token"]}
    )
    assert r.status_code == 200, r.text
    assert client.get(f"/api/jobs/{job_id}").status_code in (404, 410)


def test_delete_without_the_owner_token_is_refused(redis_client):
    """delete-no-ownership: a job id appearing in a shared results.csv URL
    used to let anyone holding it delete that job, and the endpoint's own
    docstring said so. The sharer had no idea they were handing over a delete
    capability.

    Accounts are ruled out, so ownership is possession of a secret the server
    issued exactly once, in the JobEnvelope, to whoever submitted the job. A
    results URL carries the id and not the token.
    """
    job_id = _submit("CCO\n")["job_id"]

    assert client.delete(f"/api/jobs/{job_id}").status_code == 403
    assert (
        client.delete(
            f"/api/jobs/{job_id}", params={"owner_token": "wrong-token"}
        ).status_code
        == 403
    )
    # ...and the job is still there, not half-deleted by the refused attempt.
    assert client.get(f"/api/jobs/{job_id}").status_code == 200


def test_depict_returns_an_svg_for_one_molecule():
    body = client.get("/api/depict", params={"smiles": "CCO"}).json()
    assert body["depiction_svg"]
    assert body["error"] is None


def test_depict_reports_a_bad_smiles():
    body = client.get("/api/depict", params={"smiles": "not_a_smiles((("}).json()
    assert body["depiction_svg"] is None
    assert body["error"]


def test_mark_job_failed_gives_a_blown_up_job_a_terminal_state(redis_client, job_id):
    """I5: mark_job_failed had ZERO test coverage of any kind.

    It is the only thing that turns a job that raised into a terminal state
    and frees the submitter's concurrent-job slot. A previous round deferred
    testing it on the reasoning that it "cannot be exercised under
    task_eager_propagates=True" -- that is wrong. An errback is a plain
    function; calling .run() with the three arguments Celery passes an
    errback (request, exc, traceback) plus the bound job_id exercises the
    real body, no worker and no broker needed.
    """
    ip = "203.0.113.55"
    redis_store.create_job(job_id, total=3, fmt="smiles_list", client_ip=ip)
    redis_store.set_job_status(job_id, "running")
    redis_client.sadd(redis_store.ip_jobs_key(ip), job_id)

    tasks.mark_job_failed.run(None, RuntimeError("boom"), None, job_id)

    meta = redis_store.read_job_meta(job_id)
    assert meta["status"] == "failed", (
        "a job whose task raised is still 'running'; the caller polls a "
        "progress bar that will not move until the 24h TTL turns it into a 404"
    )
    assert not redis_client.sismember(redis_store.ip_jobs_key(ip), job_id), (
        "the failed job still holds one of this IP's 2 concurrent slots"
    )


def test_the_fast_job_path_attaches_an_errback_like_the_batch_path_does(
    monkeypatch, redis_client
):
    """I5: translate_job_inline was dispatched with no errback at all, while
    the chord path wires mark_job_failed on every header task AND the body
    (tasks.dispatch_batch).

    That is the DEFAULT route -- every job at or under
    FAST_PATH_MAX_MOLECULES. write_chunk, bump_job_done and _close_job are
    all unguarded inside translate_job_inline, so a raise in any of them
    strands the job at 'running' for 24 hours and permanently burns one of
    that IP's two concurrent slots. The batch path recovers from exactly the
    same failure; the more-travelled path did not.

    Asserts on the errback actually handed to Celery rather than on a
    downstream side effect: under task_always_eager an errback is not
    invoked the way a real worker invokes it, so a behavioural assertion
    here would pass whether or not the errback was ever attached.
    """
    captured: dict = {}

    def _fake_apply_async(*args, **kwargs):
        captured.update(kwargs)
        return None

    monkeypatch.setattr(
        tasks.translate_job_inline, "apply_async", _fake_apply_async
    )
    molecules = [
        ParsedMolecule(index=0, raw_input="CCO", input_id=None, smiles="CCO", error=None)
    ]
    jobs_api.admit_and_dispatch("203.0.113.56", molecules, "smiles_list", True)

    errback = captured.get("link_error")
    assert errback is not None, (
        "the fast job path dispatches with no errback; a raise inside "
        "translate_job_inline leaves the job 'running' and its slot held"
    )
    assert errback.task == "app.tasks.mark_job_failed"


def test_an_uploaded_file_can_ask_for_verified_names_only(redis_client, monkeypatch):
    """upload-forces-best-effort: the file branch of _read_input returned a
    hardcoded True, while the JSON branch honoured the caller.

    best_effort=False is the caller saying "give me only names OPSIN
    round-trip verified; abstain rather than guess". A file uploader could
    not say it at all -- no multipart field existed -- so they silently got
    OPSIN-unverified names in results.csv with nothing recording that their
    request had been overridden. PRODUCT.md principle 3 ("PIN-vs-fallback-vs-
    best-effort status must be visible wherever a name appears") failing at
    the request level rather than the display level.

    Asserts on what reaches admit_and_dispatch, because whether any
    particular molecule then degrades to abstain depends on the engine, and
    this is a plumbing defect, not an engine one.
    """
    seen: dict = {}

    def _capture(ip, molecules, fmt, best_effort, verify=True):
        seen["best_effort"] = best_effort
        seen["verify"] = verify
        from app.schemas import JobEnvelope

        return JobEnvelope(
            job_id="job-be-probe", molecule_count=len(molecules), status="queued", owner_token="tok"
        )

    monkeypatch.setattr(jobs_api, "admit_and_dispatch", _capture)
    c = TestClient(app)
    r = c.post(
        "/api/jobs",
        files={"file": ("in.smi", b"CCO\nCCC\n", "chemical/x-daylight-smiles")},
        data={"best_effort": "false"},
    )

    assert r.status_code == 200, r.text
    assert seen.get("best_effort") is False, (
        "an uploaded file cannot ask for verified-only names; the file branch "
        "forces best_effort=True regardless of what the caller sent"
    )


def test_an_uploaded_file_still_defaults_to_best_effort(redis_client, monkeypatch):
    """The good-case half: adding the override must not change the default
    for every existing caller, who sends no such field. TextPayload's own
    default is True, so the two branches have to agree.
    """
    seen: dict = {}

    def _capture(ip, molecules, fmt, best_effort, verify=True):
        seen["best_effort"] = best_effort
        seen["verify"] = verify
        from app.schemas import JobEnvelope

        return JobEnvelope(
            job_id="job-be-probe-2", molecule_count=len(molecules), status="queued", owner_token="tok"
        )

    monkeypatch.setattr(jobs_api, "admit_and_dispatch", _capture)
    c = TestClient(app)
    r = c.post(
        "/api/jobs",
        files={"file": ("in.smi", b"CCO\n", "chemical/x-daylight-smiles")},
    )

    assert r.status_code == 200, r.text
    assert seen.get("best_effort") is True, "the default changed for existing callers"


# Hardcoded, NOT parametrized over jobs_api._FORMULA_LEADERS. Deriving the
# cases from the tuple under test means narrowing that tuple silently narrows
# the test matrix too: a mutation run that cut it to ("=",) left this test
# "2 passed" instead of failing. The whole point is to notice a leader being
# dropped, so the expectation has to live here.
_EXPECTED_FORMULA_LEADERS = ("=", "+", "-", "@", "\t", "\r")


@pytest.mark.parametrize("leader", _EXPECTED_FORMULA_LEADERS)
@pytest.mark.parametrize("column", ["input", "error"])
def test_every_formula_leader_is_neutralised_in_every_user_text_column(
    redis_client, job_id, leader, column
):
    """csv-injection-partial-test: _FORMULA_LEADERS has six entries and only
    "=" was ever exercised, on the "input" column only.

    CSV injection: a spreadsheet treats a cell starting with any of these as
    a formula, so untrusted text can execute when the user opens the file
    they downloaded. Narrowing the tuple to "=", or dropping _csv_safe from
    the "error" column -- which jobs_api names as the other verbatim
    user-text field -- kept the whole suite green while leaving five vectors
    live.

    "-" and "@" matter most of the six: both occur naturally at the head of
    chemical text, so they are the ones a reviewer is most tempted to drop as
    false positives.
    """
    payload = leader + "cmd|' /c calc'!A1"
    row = {"index": 0, "input": "CCO", "status": "error", "error": None}
    row[column] = payload

    redis_store.create_job(job_id, total=1, fmt="smiles_list", client_ip="::1")
    redis_store.write_chunk(job_id, 0, [row])
    redis_store.assemble_rows(job_id, n_chunks=1)
    redis_store.set_job_status(job_id, "done")

    body = TestClient(app).get(f"/api/jobs/{job_id}/results.csv").text

    # Assert on the whole body, not body.splitlines()[1]: a leading "\r" is
    # correctly escaped AND quoted by the csv writer, and the quoted CR then
    # splits the "line" -- a first draft asserted on line 1 and reported a
    # false failure for that one leader while the guard was working.
    assert "'" + payload in body, (
        f"{leader!r} reached the {column} column unescaped; a spreadsheet "
        "would evaluate it as a formula when the user opens their download"
    )


def test_a_multipart_upload_with_no_file_part_is_a_400_not_a_500(redis_client):
    """upload-branch-untested: `grep -rn "files=" backend/tests/` returned
    ZERO hits before this. Every test posted JSON, so the entire
    `if file is not None:` branch of _read_input -- the only user-facing
    route into the batch pipeline -- never executed.

    This case is named by hand in _read_input's own docstring: a multipart
    request with no `file` part has already had its body stream consumed by
    the time FastAPI resolves `file` to None, so falling through to
    request.json() raises a bare RuntimeError("Stream consumed") that would
    surface as a 500. The docstring says it is handled; nothing checked.
    """
    r = TestClient(app).post(
        "/api/jobs", files={"notthefile": ("x.txt", b"CCO\n", "text/plain")}
    )
    assert r.status_code == 400, (
        f"got {r.status_code}; a malformed request is the caller's mistake to "
        "be told about, not the server's to crash on"
    )


def test_an_uploaded_file_over_the_size_limit_is_rejected(redis_client, monkeypatch):
    """translate-body-size-untested: the two existing "limit" tests both
    monkeypatch MAX_BATCH_SIZE, which is the molecule COUNT cap -- a
    different thing. Every byte-limit site was uncovered, including this one,
    so the guard could be deleted or mis-scoped with the suite green.
    """
    monkeypatch.setattr(get_settings(), "MAX_FILE_SIZE_MB", 1)
    oversized = b"CCO\n" * 300_000  # ~1.2 MB

    r = TestClient(app).post(
        "/api/jobs", files={"file": ("big.smi", oversized, "text/plain")}
    )
    assert r.status_code == 413, f"got {r.status_code}; the size cap did not bind"


def test_the_declared_size_and_the_actual_size_are_both_checked():
    """Both halves of _read_input's size guard exist, and the test above
    exercises only the first.

    TestClient always sends a Content-Length, so the pre-read check fires and
    the post-read one is never reached -- confirmed by mutation: deleting the
    post-read check leaves that test passing. The post-read check exists for
    the case Content-Length is absent (chunked transfer) or a lie, which
    TestClient cannot produce, so this asserts the guard is present rather
    than driving it. Honest coverage of a real gap beats a test that pretends
    to close it.
    """
    import inspect

    source = inspect.getsource(jobs_api._read_input)
    assert source.count("max_file_size_bytes") >= 3, (
        "one of _read_input's size checks is gone; a body with no "
        "Content-Length, or a lying one, is now unbounded"
    )


def test_an_oversized_json_body_is_rejected_on_translate(monkeypatch):
    """The other byte-limit site: the /api/translate request-size middleware.
    It exists because "a single 100 MB SMILES string was accepted" -- and it
    could be deleted, or its path prefix mis-scoped, with nothing failing.
    """
    monkeypatch.setattr(get_settings(), "MAX_FILE_SIZE_MB", 1)
    r = TestClient(app).post(
        "/api/translate", json={"smiles": ["C" * 2_000_000], "best_effort": True}
    )
    assert r.status_code == 413, f"got {r.status_code}; the middleware did not bind"


def test_a_job_whose_meta_was_evicted_mid_flight_reports_gone_not_never_existed(
    redis_client, job_id
):
    """CC3-preclose-meta-eviction: reproduced live.

    Write chunk 0, evict the meta hash, then close. _close_job finds no meta,
    logs "meta hash missing at close" and returns 0 WITHOUT calling
    assemble_rows -- correctly, since the declared total is gone and
    completeness cannot be verified. But the rows key is therefore never
    created, and _meta_or_error's 410-vs-404 decision hinges on that key
    existing. So the caller was told "No such job" about a job they
    definitely submitted, while its chunk sat in Redis on a 24-hour TTL.

    Spec section 10 promises 410 Gone, "distinct from never having existed",
    precisely so a user can tell "your results aged out" from "you have the
    wrong link". test_jobs_api's existing coverage only exercised eviction
    AFTER a successful close.
    """
    redis_store.create_job(job_id, total=2, fmt="smiles_list", client_ip="::1")
    redis_store.write_chunk(job_id, 0, [{"index": 0, "input": "CCO", "status": "pin"}])
    redis_client.delete(redis_store.job_meta_key(job_id))

    tasks._close_job(job_id, n_chunks=1)

    r = TestClient(app).get(f"/api/jobs/{job_id}")
    assert r.status_code == 410, (
        f"got {r.status_code}; a job whose meta was evicted before it closed "
        "is reported as never having existed"
    )


def test_a_job_id_that_never_existed_is_still_a_404(redis_client):
    """The other half. Widening the 410 test must not turn every unknown id
    into "expired" -- a user who mistypes a link needs to be told it is
    wrong, not that their results aged out.
    """
    r = TestClient(app).get("/api/jobs/ffffffffffffffffffffffffffffffff")
    assert r.status_code == 404, f"got {r.status_code}; an unknown id must be 404"


def test_cancelling_a_job_stops_queued_chunks_from_naming_anything(redis_client, job_id):
    """job-cancellation: cancellation is cooperative and reuses begin_chunk.

    Celery cannot interrupt a running task, and revoking one already in flight
    is unreliable, so nothing tries. Writing the terminal status "cancelled"
    is the whole mechanism: begin_chunk already refuses to start another chunk
    for a terminal job, so every chunk still queued returns having named
    nothing. A chunk already executing finishes that chunk -- bounded by
    BATCH_CHUNK_SIZE, not by the rest of the job.

    Drives redis_store.begin_chunk directly, because that IS the enforcement
    point; asserting on a task's return value would test Celery's plumbing
    instead.
    """
    redis_store.create_job(job_id, total=100, fmt="smiles_list", client_ip="::1")
    assert redis_store.begin_chunk(job_id) is True, "a live job must accept chunks"

    redis_store.set_job_status(job_id, "cancelled")

    assert redis_store.begin_chunk(job_id) is False, (
        "a cancelled job still accepts new chunks, so cancelling it does not "
        "actually stop the work -- it only relabels it"
    )


def test_cancelling_frees_the_concurrent_slot(redis_client, job_id):
    """The reason cancellation is worth having at all: a user who submits
    10,000 molecules by mistake held one of their two concurrent slots for the
    whole ~80-minute run, with no way out. DELETE refused a non-terminal job
    outright, and correctly so -- deleting the meta while chunks kept running
    neither stopped the work nor protected the cap.
    """
    ip = "203.0.113.77"
    # Built directly rather than through _submit: under eager Celery a
    # submitted job runs to completion inside the request, and set_job_status
    # now REFUSES to move a terminal job back to "running" -- which is the
    # whole point of the compare-and-set. A test that needs a live job has to
    # start with one.
    jid, token = "job-cancel-slot", "owner-token-for-cancel"
    redis_store.create_job(jid, total=100, fmt="smiles_list", client_ip=ip, owner_token=token)
    redis_store.set_job_status(jid, "running")
    redis_client.sadd(redis_store.ip_jobs_key(ip), jid)

    r = client.post(f"/api/jobs/{jid}/cancel", params={"owner_token": token})

    assert r.status_code == 200, r.text
    assert r.json()["status"] == "cancelled"
    assert not redis_client.sismember(redis_store.ip_jobs_key(ip), jid), (
        "the cancelled job still holds one of this IP's concurrent slots"
    )


def test_cancelling_a_finished_job_does_not_relabel_it(redis_client):
    """Idempotent, and it must not resurrect or rewrite a real outcome: a job
    that genuinely completed stays done. Reporting "cancelled" over a
    completed result would be a lie about what the engine produced.
    """
    envelope = _submit("CCO\n")
    jid, token = envelope["job_id"], envelope["owner_token"]
    assert client.get(f"/api/jobs/{jid}").json()["status"] == "done"

    r = client.post(f"/api/jobs/{jid}/cancel", params={"owner_token": token})

    assert r.status_code == 200, r.text
    assert r.json()["status"] == "done", "a completed job was relabelled cancelled"


def test_cancelling_needs_the_owner_token(redis_client):
    """Same capability as delete, same gate. Otherwise anyone shown a results
    link could kill the job that produced it.
    """
    jid = _submit("CCO\n")["job_id"]
    assert client.post(f"/api/jobs/{jid}/cancel").status_code == 403
    assert (
        client.post(f"/api/jobs/{jid}/cancel", params={"owner_token": "nope"}).status_code
        == 403
    )


def test_the_status_endpoint_never_leaks_the_owner_token(redis_client):
    """The token is a capability. It is returned exactly once, in the
    JobEnvelope, and no read endpoint may hand it back -- otherwise anyone who
    can poll a job id can delete it, and the ownership check is theatre.
    """
    envelope = _submit("CCO\n")
    jid, token = envelope["job_id"], envelope["owner_token"]

    body = client.get(f"/api/jobs/{jid}").json()
    assert "owner" not in body and "owner_token" not in body
    assert token not in str(body)


def test_the_upload_parse_is_dispatched_to_a_worker(monkeypatch, redis_client):
    """Spec section 13a / parse-cost-aggregate: parsing an upload is RDKit
    work, and RDKit's Boost.Python wrappers do not release the GIL, so doing
    it in the web process blocks every other request there for its duration.
    FastAPI's threadpool does not help.

    Measured, which is what settled the design: cost scales with molecule SIZE
    rather than count. 10,000 short SMILES parse in 0.14 s, but 1,000 at
    MAX_MOLECULE_SMILES_LENGTH take 29.1 s -- so a full 10,000-molecule upload
    of large molecules is roughly 290 s of GIL-held CPU from one request well
    inside its quota. The molecule-count caps never bounded it, because they
    count molecules.

    Asserts the dispatch happens, not a downstream effect: under
    task_always_eager the task runs inline in this very process, so any
    behavioural assertion would pass whether or not anything was dispatched.
    """
    dispatched: dict = {}
    real = tasks.parse_input.apply_async

    def _spy(*args, **kwargs):
        dispatched["queue"] = kwargs.get("queue")
        return real(*args, **kwargs)

    monkeypatch.setattr(tasks.parse_input, "apply_async", _spy)

    r = client.post("/api/jobs", json={"text": "CCO\nCCC\n"})

    assert r.status_code == 200, r.text
    assert dispatched.get("queue") == "batch", (
        "the upload was parsed in the web process, holding the GIL against "
        "every other request"
    )


def test_a_malformed_upload_still_fails_synchronously_with_a_reason(redis_client):
    """The contract this change had to preserve, and the reason the caller
    BLOCKS on the parse rather than being handed a job envelope.

    A CSV with no smiles column must still come back as an immediate 400 that
    names the problem. Accepting it and failing asynchronously ten seconds
    later, with nowhere to report why, would have been a real regression
    dressed up as an optimisation.
    """
    # A CSV whose header names no `smiles` column. Sniffed as CSV because the
    # header contains "smiles" and a delimiter; rejected during the parse
    # because "smiles_x" is not "smiles".
    r = client.post("/api/jobs", json={"text": "smiles_x,id\nCCO,a\n"})

    assert r.status_code == 400, r.text
    assert "smiles" in r.text.lower()

    # And an input that parses cleanly to nothing at all.
    empty = client.post("/api/jobs", json={"text": "   \n  \n"})
    assert empty.status_code == 400, empty.text


def test_the_parse_falls_back_in_process_when_no_worker_answers(monkeypatch, redis_client):
    """A valid upload must not 503 because the batch queue is idle.

    This is the honest limit of the change: the CPU moves whenever a worker is
    available, and when one is not, behaviour is exactly what it was before.
    Never worse, which is what makes it safe to ship without an operational
    prerequisite.
    """
    class _NeverPickedUp:
        """A task nobody ever accepts: state stays PENDING forever.

        That -- not a completion timeout -- is what the fallback keys off.
        Waiting for completion was tried and is wrong: at 30.7 ms/molecule the
        crossover is ~977 molecules, so every upload above that timed out, was
        re-parsed in the web process, AND left the abandoned worker parsing
        the same bytes.
        """

        state = "PENDING"

        def get(self, timeout=None):
            raise AssertionError("get() must not be called before a worker starts")

        def revoke(self):
            pass

        def forget(self):
            pass

    monkeypatch.setattr(get_settings(), "PARSE_TIMEOUT", 1)
    monkeypatch.setattr(
        tasks.parse_input, "apply_async", lambda *a, **k: _NeverPickedUp()
    )

    r = client.post("/api/jobs", json={"text": "CCO\nCCC\n"})

    assert r.status_code == 200, r.text
    assert r.json()["molecule_count"] == 2


def test_a_cancelled_job_survives_the_close_that_follows_it(redis_client):
    """The half of cancellation that begin_chunk does NOT cover, and which
    shipped broken.

    begin_chunk guards WORK STARTING. It does not guard STATUS WRITING, and
    three writers bypass it: _close_job writes "done" or "failed", and
    mark_job_failed writes "failed". Celery skips a chord BODY only when a
    header task FAILS -- a cancelled chunk returns normally, so the body fires,
    _close_job runs, and it wrote straight over "cancelled".

    Measured before the fix: cancel -> begin_chunk correctly refuses ->
    _close_job -> status "failed". The user who cancelled saw a failure and a
    -partial CSV, and if every chunk had happened to be in flight when the
    cancel landed, a resurrected "done".

    set_job_status is now a compare-and-set that refuses to move a job out of
    a terminal state, so all four writers inherit the rule.
    """
    jid = "job-cancel-survives"
    redis_store.create_job(jid, total=2, fmt="smiles_list", client_ip="::1")
    redis_store.write_chunk(jid, 0, [{"index": 0, "input": "CCO", "status": "pin"}])
    redis_store.set_job_status(jid, "cancelled")

    tasks._close_job(jid, n_chunks=1)
    assert redis_store.read_job_meta(jid)["status"] == "cancelled", (
        "_close_job overwrote the cancellation"
    )

    tasks.mark_job_failed.run(None, RuntimeError("boom"), None, jid)
    assert redis_store.read_job_meta(jid)["status"] == "cancelled", (
        "mark_job_failed overwrote the cancellation"
    )


def test_a_live_job_can_still_change_status(redis_client):
    """The good-case half. A compare-and-set that refuses everything is not a
    guard, it is a job that never progresses -- so a non-terminal job must
    still move freely.
    """
    jid = "job-status-live"
    redis_store.create_job(jid, total=1, fmt="smiles_list", client_ip="::1")

    assert redis_store.set_job_status(jid, "running") is True
    assert redis_store.read_job_meta(jid)["status"] == "running"
    assert redis_store.set_job_status(jid, "done") is True
    assert redis_store.read_job_meta(jid)["status"] == "done"
    # ...and now it is terminal, so it stops moving.
    assert redis_store.set_job_status(jid, "running") is False
    assert redis_store.read_job_meta(jid)["status"] == "done"
