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


def test_translate_returns_empty_results_for_an_empty_list(redis_client):
    # Round 1 review, Important: this used to 400. frontend/src/lib/api.js
    # throws on a non-2xx response and nobody decided this should change --
    # restored to the original 200-with-empty-results behaviour. An empty
    # submission does no work, so it must not need a live worker JVM either.
    response = client.post("/api/translate", json={"smiles": []})
    assert response.status_code == 200
    assert response.json() == {"results": []}


def test_translate_returns_empty_results_for_an_all_blank_list(redis_client):
    response = client.post("/api/translate", json={"smiles": ["   ", ""]})
    assert response.status_code == 200
    assert response.json() == {"results": []}


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
    require_a_live_jvm from an endpoint) still left every test green.

    Includes POST /api/jobs (round 2 review, Also-fix): the batch path
    named molecules with no verified JVM anywhere, the exact fail-open this
    rule exists to prevent, on the endpoint that produces the artefact
    users keep.
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
    assert (
        client.post("/api/jobs", json={"text": "CCO\n"}).status_code == 503
    )


def test_importing_main_does_not_start_a_jvm():
    """The web process must never start a JVM -- this task's headline
    claim, tested for real. opsin_decompose.self_check() (called via the
    old startup hook, since removed) reaches opsin_available() ->
    _ensure_jvm() -> jpype.startJVM(), so every uvicorn worker would boot
    its own 512 MB JVM. OPSIN now lives only in Celery workers
    (celery_app._start_child_jvm calls self_check() in each forked child).

    Round 2 review: a source grep (the previous version of this test) is
    defeated by a comment naming the module, and passed by code that
    imports it indirectly through importlib or a re-export -- it tests the
    text of main.py, not the claim. A subprocess is required regardless:
    the test suite's OWN process already has a JVM started (test_api.py's
    eager-mode explain calls), so "no JVM started" cannot be asserted from
    within this same process no matter how it is checked.
    """
    import os
    import subprocess
    import sys
    from pathlib import Path

    backend_root = Path(__file__).resolve().parent.parent
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import app.main; import jpype; print(jpype.isJVMStarted())",
        ],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(backend_root),
        env={
            **os.environ,
            "PYTHONPATH": str(backend_root),
            "REDIS_URL": os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
        },
    )
    assert result.stdout.strip() == "False", (
        "importing app.main started a JVM.\n"
        f"stdout: {result.stdout!r}\nstderr: {result.stderr[-3000:]!r}"
    )


class _FakeTimedOutResult:
    """Stands in for an AsyncResult whose .get(timeout=...) never got an
    answer in time, without needing a real broker/worker round trip.
    """

    def get(self, timeout=None):
        from celery.exceptions import TimeoutError as CeleryTimeoutError

        raise CeleryTimeoutError("simulated timeout for testing")


def test_translate_returns_a_job_envelope_on_timeout(redis_client, monkeypatch):
    """Round 1 review, Critical 4: nothing caught celery.exceptions.
    TimeoutError at all -- it escaped as a bare 500, even though
    schemas.JobEnvelope's own docstring promises a job envelope on timeout.
    /api/translate DOES have job machinery, so on timeout it must fall back
    to a real, pollable job rather than failing the request.
    """
    from app import main as main_module

    monkeypatch.setattr(
        main_module.translate_fast,
        "apply_async",
        lambda *a, **k: _FakeTimedOutResult(),
    )
    response = client.post("/api/translate", json={"smiles": ["CCO"]})
    assert response.status_code == 200
    body = response.json()
    assert "job_id" in body
    assert body["molecule_count"] == 1

    # The fallback job is real and pollable -- translate_job_inline still
    # runs eagerly (a different task, not the one monkeypatched above), so
    # it has already completed.
    status = client.get(f"/api/jobs/{body['job_id']}").json()
    assert status["status"] == "done"


def test_iupac_to_smiles_returns_504_on_timeout(redis_client, monkeypatch):
    """/api/iupac-to-smiles has no job store behind it, so a JobEnvelope
    here would be a lie -- a deliberate departure from a literal "return a
    union" reading, recorded rather than silently decided.
    """
    from app import main as main_module

    monkeypatch.setattr(
        main_module.name_to_smiles,
        "apply_async",
        lambda *a, **k: _FakeTimedOutResult(),
    )
    response = client.get("/api/iupac-to-smiles", params={"name": "ethanol"})
    assert response.status_code == 504


def test_explain_returns_504_on_timeout(redis_client, monkeypatch):
    from app import main as main_module

    monkeypatch.setattr(
        main_module.explain_smiles,
        "apply_async",
        lambda *a, **k: _FakeTimedOutResult(),
    )
    response = client.get("/api/explain", params={"smiles": "CCO"})
    assert response.status_code == 504


def test_explain_name_returns_504_on_timeout(redis_client, monkeypatch):
    from app import main as main_module

    monkeypatch.setattr(
        main_module.explain_iupac_name,
        "apply_async",
        lambda *a, **k: _FakeTimedOutResult(),
    )
    response = client.get("/api/explain-name", params={"name": "ethanol"})
    assert response.status_code == 504


def test_translate_blank_list_still_counts_against_the_fast_cap(
    redis_client, monkeypatch
):
    """Round 2 review, finding 4, measured: three requests of an all-blank
    `smiles` list with the cap at 1 came back 200, 200, 200 with no
    counter key ever written -- the empty-list short-circuit ran BEFORE
    check_fast_allowed, making /api/translate an unlimited-rate endpoint
    for anyone who pads the body with whitespace instead of real SMILES.
    The 200-with-empty-results contract itself is unchanged.
    """
    from app.core.config import get_settings

    monkeypatch.setattr(
        get_settings(), "RATE_LIMIT_FAST_PER_MINUTE", 1, raising=False
    )
    first = client.post("/api/translate", json={"smiles": ["   ", ""]})
    second = client.post("/api/translate", json={"smiles": ["  "]})
    assert first.status_code == 200
    assert first.json() == {"results": []}
    assert second.status_code == 429


def test_translate_over_http_enforces_the_fast_per_minute_cap(
    redis_client, monkeypatch
):
    """Round 1 review, Important: deleting check_fast_allowed from all
    four main.py endpoint bodies used to leave every test green, because
    nothing exercised the cap over real HTTP -- only
    ratelimit.check_fast_allowed directly, in tests/test_rate_limit.py.
    """
    from app.core.config import get_settings

    monkeypatch.setattr(
        get_settings(), "RATE_LIMIT_FAST_PER_MINUTE", 2, raising=False
    )
    assert client.post("/api/translate", json={"smiles": ["CCO"]}).status_code == 200
    assert client.post("/api/translate", json={"smiles": ["CCC"]}).status_code == 200
    assert client.post("/api/translate", json={"smiles": ["CCCC"]}).status_code == 429


def test_explain_over_http_enforces_the_fast_per_minute_cap(
    redis_client, monkeypatch
):
    # Round 2 review, coverage gap: deleting check_fast_allowed from any
    # one of the three explain/iupac endpoints alone stayed green before.
    from app.core.config import get_settings

    monkeypatch.setattr(
        get_settings(), "RATE_LIMIT_FAST_PER_MINUTE", 1, raising=False
    )
    assert client.get("/api/explain", params={"smiles": "CCO"}).status_code == 200
    assert client.get("/api/explain", params={"smiles": "CCC"}).status_code == 429


def test_explain_name_over_http_enforces_the_fast_per_minute_cap(
    redis_client, monkeypatch
):
    from app.core.config import get_settings

    monkeypatch.setattr(
        get_settings(), "RATE_LIMIT_FAST_PER_MINUTE", 1, raising=False
    )
    assert (
        client.get("/api/explain-name", params={"name": "ethanol"}).status_code
        == 200
    )
    assert (
        client.get("/api/explain-name", params={"name": "ethanol"}).status_code
        == 429
    )


def test_iupac_to_smiles_over_http_enforces_the_fast_per_minute_cap(
    redis_client, monkeypatch
):
    from app.core.config import get_settings

    monkeypatch.setattr(
        get_settings(), "RATE_LIMIT_FAST_PER_MINUTE", 1, raising=False
    )
    assert (
        client.get("/api/iupac-to-smiles", params={"name": "ethanol"}).status_code
        == 200
    )
    assert (
        client.get("/api/iupac-to-smiles", params={"name": "ethanol"}).status_code
        == 429
    )
