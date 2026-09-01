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


def test_an_oversized_smiles_on_the_fast_path_never_reaches_rdkit(
    redis_client, monkeypatch
):
    """Final review, crash-loop fix: a 30,000-character SMILES SIGSEGVs
    RDKit's Chem.MolToSmiles (measured: clean at 20k atoms, crash at 30k
    and 50k). Because task_acks_late=True and
    task_reject_on_worker_lost=True, a SIGKILLed task is requeued, so one
    such request could crash-loop the fast queue forever. Before this
    fix, translate_fast handed raw user text straight to
    translate_one -> Chem.MolFromSmiles/MolToSmiles with no length check
    at all, unlike every other input path.

    This does NOT reproduce the segfault (that would crash the whole test
    process) -- it proves the guard instead: monkeypatch translate_one to
    raise if it is ever called with the oversized string, so the test
    fails loudly if the length check is ever bypassed, rather than
    silently letting an oversized molecule reach RDKit again.
    """
    import app.tasks as tasks_module

    real_translate_one = tasks_module.translate_one
    oversized = "C" * 30000

    def guarded_translate_one(smiles, best_effort=True):
        assert smiles != oversized, (
            "the oversized SMILES reached translate_one -- "
            "MAX_MOLECULE_SMILES_LENGTH did not gate it before RDKit"
        )
        return real_translate_one(smiles, best_effort=best_effort)

    monkeypatch.setattr(tasks_module, "translate_one", guarded_translate_one)

    response = client.post(
        "/api/translate", json={"smiles": ["CCO", oversized, "CCC"]}
    )
    assert response.status_code == 200, response.text
    results = response.json()["results"]
    assert [r["status"] for r in results] == ["pin", "error", "pin"]
    assert results[1]["error"] == "SMILES string exceeds 2000 characters"
    # The response still echoes the caller's original text for the
    # rejected row, same convention translate_one itself uses for an
    # unparseable string.
    assert results[1]["smiles"] == oversized


def test_translate_above_the_fast_limit_returns_a_job_envelope(
    redis_client, monkeypatch
):
    from app.core.config import get_settings

    monkeypatch.setattr(
        get_settings(), "FAST_PATH_MAX_MOLECULES", 1
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


def test_jobs_503_does_not_burn_the_hourly_quota(redis_client, no_worker_opsin):
    """Round 4 review, finding 2: check_job_allowed used to run BEFORE
    require_a_live_jvm in create_job, so every POST /api/jobs during a JVM
    outage burned one of the caller's RATE_LIMIT_JOBS_PER_HOUR units
    before returning 503 -- while /api/translate, which already gated on
    the JVM first, cost its callers nothing for the same outage. A client
    that retries during an outage could exhaust its hourly quota and stay
    locked out of batch submission for up to an hour AFTER service
    recovers -- punishing a user for the outage, not their own usage.
    """
    for key in redis_client.scan_iter(match="stitch:ip:testclient:hour:*"):
        redis_client.delete(key)

    response = client.post("/api/jobs", json={"text": "CCO\n"})
    assert response.status_code == 503

    hour_keys = list(
        redis_client.scan_iter(match="stitch:ip:testclient:hour:*")
    )
    assert not hour_keys, (
        "a 503 (no live JVM) must not touch the hourly job-submission "
        "counter"
    )


def test_jobs_over_http_enforces_the_fast_per_minute_cap(
    redis_client, monkeypatch
):
    """Round 5 review, finding 1: round 4's fix moved require_a_live_jvm
    ahead of check_job_allowed in create_job, which correctly stopped a
    JVM outage from burning the caller's hourly job quota (see
    test_jobs_503_does_not_burn_the_hourly_quota, above) -- but left
    check_job_allowed as the only limiter on this endpoint at all, so
    require_a_live_jvm became reachable an unbounded number of times per
    minute. /api/translate already gates the same way (check_fast_allowed
    first, then require_a_live_jvm) -- POST /api/jobs now matches that
    shape, same as the three explain/iupac endpoints below.
    """
    from app.core.config import get_settings

    monkeypatch.setattr(
        get_settings(), "RATE_LIMIT_FAST_PER_MINUTE", 1
    )
    first = client.post("/api/jobs", json={"text": "CCO\n"})
    assert first.status_code == 200
    second = client.post("/api/jobs", json={"text": "CCC\n"})
    assert second.status_code == 429


def test_jobs_checks_the_job_cap_before_parsing(redis_client, monkeypatch):
    """Round 4 review, note 3: nothing protected finding 1's ORDERING
    claim itself -- a future refactor could silently move
    check_job_allowed back to after the parse (its old, 46-second-parse-
    before-429 position) without any test failing, since the eventual
    outcome (a 429 or a 200) looks identical either way. Spies on the call
    order directly, cheaply, rather than relying on a slow real parse to
    prove which ran first.
    """
    import app.jobs_api as jobs_api_module

    order: list[str] = []
    real_check = jobs_api_module.check_job_allowed
    real_parse = jobs_api_module._parse_or_400

    def spy_check(ip):
        order.append("check_job_allowed")
        return real_check(ip)

    def spy_parse(data, max_molecules):
        order.append("_parse_or_400")
        return real_parse(data, max_molecules)

    monkeypatch.setattr(jobs_api_module, "check_job_allowed", spy_check)
    monkeypatch.setattr(jobs_api_module, "_parse_or_400", spy_parse)

    response = client.post("/api/jobs", json={"text": "CCO\n"})
    assert response.status_code == 200, response.text
    assert order == ["check_job_allowed", "_parse_or_400"], order


def test_translate_checks_the_job_cap_before_canonicalizing(
    redis_client, monkeypatch
):
    """Same ordering guarantee as above, for /api/translate's job-dispatch
    branch -- check_job_allowed before _canonicalize, not after.
    """
    import app.main as main_module
    from app.core.config import get_settings

    monkeypatch.setattr(
        get_settings(), "FAST_PATH_MAX_MOLECULES", 1
    )

    order: list[str] = []
    real_check = main_module.check_job_allowed
    real_canonicalize = main_module._canonicalize

    def spy_check(ip):
        order.append("check_job_allowed")
        return real_check(ip)

    def spy_canonicalize(smiles_list, max_molecules):
        order.append("_canonicalize")
        return real_canonicalize(smiles_list, max_molecules)

    monkeypatch.setattr(main_module, "check_job_allowed", spy_check)
    monkeypatch.setattr(main_module, "_canonicalize", spy_canonicalize)

    response = client.post("/api/translate", json={"smiles": ["CCO", "CCC"]})
    assert response.status_code == 200, response.text
    assert order == ["check_job_allowed", "_canonicalize"], order


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
        get_settings(), "RATE_LIMIT_FAST_PER_MINUTE", 1
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
        get_settings(), "RATE_LIMIT_FAST_PER_MINUTE", 2
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
        get_settings(), "RATE_LIMIT_FAST_PER_MINUTE", 1
    )
    assert client.get("/api/explain", params={"smiles": "CCO"}).status_code == 200
    assert client.get("/api/explain", params={"smiles": "CCC"}).status_code == 429


def test_explain_name_over_http_enforces_the_fast_per_minute_cap(
    redis_client, monkeypatch
):
    from app.core.config import get_settings

    monkeypatch.setattr(
        get_settings(), "RATE_LIMIT_FAST_PER_MINUTE", 1
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
        get_settings(), "RATE_LIMIT_FAST_PER_MINUTE", 1
    )
    assert (
        client.get("/api/iupac-to-smiles", params={"name": "ethanol"}).status_code
        == 200
    )
    assert (
        client.get("/api/iupac-to-smiles", params={"name": "ethanol"}).status_code
        == 429
    )


def test_one_bad_molecule_does_not_lose_the_whole_fast_request(monkeypatch):
    """I4: translate_fast's loop called translate_one with no try/except, so
    a raise on ONE molecule lost the entire request.

    _name_prepared, which the batch path uses, wraps the same call and emits
    an honest error row for that molecule while the rest survive
    ("one bad molecule must not lose the other 24 in its chunk"). main.py
    catches only CeleryTimeoutError, so on the fast path the raise reached
    the client as a bare 500 with no detail -- on Home, the main product
    surface.

    This is not hypothetical: the last upstream tier rename made classify()
    raise ValueError on live rows, and it will happen again on the next one.
    """
    from app import tasks

    real = tasks.translate_one

    def _explode_on_the_second(smiles, best_effort=True):
        if smiles == "CCC":
            raise ValueError("Unexpected name_tiered() row, cannot classify")
        return real(smiles, best_effort=best_effort)

    monkeypatch.setattr(tasks, "translate_one", _explode_on_the_second)
    monkeypatch.setattr(tasks.name_cache, "get_cached", lambda *a, **k: None)
    monkeypatch.setattr(tasks.name_cache, "put_cached", lambda *a, **k: None)

    prepared = [
        {"index": 0, "raw_input": "CCO", "input_id": None, "smiles": "CCO", "error": None},
        {"index": 1, "raw_input": "CCC", "input_id": None, "smiles": "CCC", "error": None},
        {"index": 2, "raw_input": "CCCC", "input_id": None, "smiles": "CCCC", "error": None},
    ]

    rows = tasks.translate_fast.run(prepared, True)

    assert len(rows) == 3, "a single raising molecule lost the whole request"
    assert rows[0]["name"], "the molecules that named fine must still be returned"
    assert rows[1]["status"] == "error"
    assert "cannot classify" in (rows[1]["error"] or "")
    assert rows[2]["name"], "the molecules AFTER the failure must still be returned"


def test_a_soft_time_limit_is_not_swallowed_by_the_per_molecule_guard(monkeypatch):
    """The interaction that makes the guard above dangerous if written
    naively: SoftTimeLimitExceeded subclasses Exception DIRECTLY, so a bare
    `except Exception` per molecule swallows Celery's timeout, the loop runs
    on past the limit, and the hard limit kills the worker mid-request with
    nothing written.

    _name_prepared already orders its handlers to avoid exactly this; the
    fast path must not reintroduce it.
    """
    from celery.exceptions import SoftTimeLimitExceeded

    from app import tasks

    assert SoftTimeLimitExceeded.__mro__[1] is Exception, (
        "SoftTimeLimitExceeded no longer subclasses Exception directly; "
        "re-check every `except Exception` that must not swallow it"
    )

    def _timeout(smiles, best_effort=True):
        raise SoftTimeLimitExceeded()

    monkeypatch.setattr(tasks, "translate_one", _timeout)
    monkeypatch.setattr(tasks.name_cache, "get_cached", lambda *a, **k: None)

    prepared = [
        {"index": 0, "raw_input": "CCO", "input_id": None, "smiles": "CCO", "error": None}
    ]

    with pytest.raises(SoftTimeLimitExceeded):
        tasks.translate_fast.run(prepared, True)
