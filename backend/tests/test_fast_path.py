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
    assert body["status"] == "OK"
    assert body["opsin"] == "available"


def test_health_degrades_without_a_live_jvm(redis_client, no_worker_opsin):
    body = client.get("/api/health").json()
    assert body["status"] == "DEGRADED"
    assert body["opsin"] == "no worker has a live JVM"


def test_naming_endpoints_503_without_a_live_jvm(redis_client, no_worker_opsin):
    """Nothing in the original 218 asserted the fail-closed rule at all --
    hardwiring any_worker_has_opsin() to True (or deleting
    _require_a_live_jvm from an endpoint) still left every test green.
    """
    assert (
        client.post("/api/translate", json={"smiles": ["CCO"]}).status_code
        == 503
    )
    assert (
        client.get(
            "/api/iupac-to-smiles", params={"name": "ethanol"}
        ).status_code
        == 503
    )
    assert (
        client.get("/api/explain", params={"smiles": "CCO"}).status_code
        == 503
    )
    assert (
        client.get(
            "/api/explain-name", params={"name": "ethanol"}
        ).status_code
        == 503
    )


def test_main_does_not_import_opsin_decompose():
    """The web process must never start a JVM -- that is this whole task's
    headline claim. opsin_decompose.self_check() (called via the old
    startup hook) reaches opsin_available() -> _ensure_jvm() ->
    jpype.startJVM(), so every uvicorn worker would boot its own 512 MB
    JVM. OPSIN now lives only in Celery workers (celery_app._start_child_jvm
    calls self_check() in each forked child).

    A source grep, not an in-process assertion: the test suite itself
    starts a JVM (test_api.py's explain endpoints, run eagerly in-process),
    so "no JVM started" cannot be asserted from within this same process --
    it would already be false by the time this test runs, for reasons that
    have nothing to do with main.py.
    """
    from pathlib import Path

    import app.main

    source = Path(app.main.__file__).read_text()
    assert "opsin_decompose" not in source
