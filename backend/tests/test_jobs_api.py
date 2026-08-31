"""Job endpoints, driven with Celery in eager mode.

Eager mode runs tasks inline, so this exercises the real task bodies, the
real Redis writes and the real assembly ordering without needing a worker
process. The forked-worker JVM behaviour is covered separately in
test_celery_jvm_fork.py -- that is the one thing eager mode cannot test.
"""

import pytest
from fastapi.testclient import TestClient

from app.celery_app import celery_app
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


def test_chunk_order_is_preserved_across_multiple_chunks(redis_client, monkeypatch):
    from app.core.config import get_settings

    settings = get_settings()
    # BOTH knobs, and the first one is the point: with FAST_PATH_MAX_MOLECULES
    # at its default 10, a 5-molecule job takes the single-task fast path and
    # never chunks at all -- so this test would pass while exercising none of
    # the chunking, chord or assembly-ordering code it is named for.
    monkeypatch.setattr(settings, "FAST_PATH_MAX_MOLECULES", 1, raising=False)
    monkeypatch.setattr(settings, "BATCH_CHUNK_SIZE", 2, raising=False)

    smiles = ["CCO", "CCC", "CCCC", "CCCCC", "c1ccccc1"]
    job_id = _submit("\n".join(smiles))["job_id"]
    rows = client.get(
        f"/api/jobs/{job_id}/results", params={"limit": 100}
    ).json()["rows"]
    assert [r["index"] for r in rows] == [0, 1, 2, 3, 4]
    assert [r["input"] for r in rows] == smiles


def test_dispatch_batch_chunks_and_assembles_in_order(redis_client, job_id):
    """The chunking path directly, including the short final chunk.

    5 molecules at chunk size 2 is 3 chunks: 2 + 2 + 1. The short last chunk
    is exactly the case where taking start_index from arithmetic
    (index * chunk_size) instead of from the data would misnumber rows.
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
    redis_client.delete(f"orthonym:job:{job_id}:meta")
    try:
        assert client.get(f"/api/jobs/{job_id}").status_code == 410
    finally:
        redis_client.delete(f"orthonym:job:{job_id}:rows")


def test_oversize_input_is_413(monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "MAX_BATCH_SIZE", 2, raising=False)
    response = client.post("/api/jobs", json={"text": "CCO\nCCC\nCCCC\n"})
    assert response.status_code == 413
    assert "2" in response.json()["detail"]


def test_delete_removes_the_job(redis_client):
    job_id = _submit("CCO\n")["job_id"]
    assert client.delete(f"/api/jobs/{job_id}").status_code == 200
    assert client.get(f"/api/jobs/{job_id}").status_code in (404, 410)


def test_depict_returns_an_svg_for_one_molecule():
    body = client.get("/api/depict", params={"smiles": "CCO"}).json()
    assert body["depiction_svg"]
    assert body["error"] is None


def test_depict_reports_a_bad_smiles():
    body = client.get("/api/depict", params={"smiles": "not_a_smiles((("}).json()
    assert body["depiction_svg"] is None
    assert body["error"]
