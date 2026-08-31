"""The fast path now runs on a worker, but its response must not change.

Existing clients depend on TranslateResponse's exact shape, so the
completed response stays byte-compatible; only the timeout case is new.
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


def test_translate_response_shape_is_unchanged(redis_client):
    response = client.post("/api/translate", json={"smiles": ["CCO"]})
    assert response.status_code == 200
    body = response.json()
    assert "results" in body
    item = body["results"][0]
    assert item["smiles"] == "CCO"
    assert item["status"] == "pin"
    assert item["name"] == "ethanol"
    # The single-molecule path keeps its picture; only batch rows drop it.
    assert item["depiction_svg"]
    assert item["roundtrip_match"] is True


def test_translate_above_the_fast_limit_returns_a_job_envelope(
    redis_client, monkeypatch
):
    from app.core.config import get_settings

    monkeypatch.setattr(
        get_settings(), "FAST_PATH_MAX_MOLECULES", 1, raising=False
    )
    response = client.post("/api/translate", json={"smiles": ["CCO", "CCC"]})
    assert response.status_code == 200
    body = response.json()
    assert "job_id" in body
    assert body["molecule_count"] == 2


def test_translate_rejects_an_empty_list(redis_client):
    response = client.post("/api/translate", json={"smiles": []})
    assert response.status_code == 400


def test_health_reports_worker_opsin_status(redis_client):
    body = client.get("/api/health").json()
    assert "status" in body
    assert "opsin" in body
