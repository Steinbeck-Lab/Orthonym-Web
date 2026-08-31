"""Shared fixtures. GOLDEN_NAMES is the fixed decomposition corpus every
later task asserts against; add to it, never reorder or remove entries.
"""

import uuid

import pytest

from app.celery_app import celery_app

CAFFEINE = "1,3,7-trimethyl-3,7-dihydro-1H-purine-2,6-dione"

GOLDEN_NAMES = [
    CAFFEINE,
    "2-[4-(2-methylpropyl)phenyl]propanoic acid",
    "2-acetyloxybenzoic acid",
    "2-amino-3-(1H-indol-3-yl)propanoic acid",
    "1,1,1-trichloro-2,2-bis(4-chlorophenyl)ethane",
    "ethyl acetate",
    "4-tert-butylcyclohexan-1-ol",
    "2-methyl-1,3,5-trinitrobenzene",
    "benzene",
    "ethanol",
]


@pytest.fixture
def caffeine_name() -> str:
    return CAFFEINE


@pytest.fixture
def redis_client():
    """A real Redis, not a fake.

    The eviction policy and the TTLs are part of what these tests assert,
    and a fake would let a wrong policy pass. If Redis is missing the tests
    FAIL with instructions rather than skipping -- a silently skipped
    integrity test is the same as no test.
    """
    from app.redis_store import get_redis

    client = get_redis()
    try:
        client.ping()
    except Exception as exc:  # noqa: BLE001 - message matters more than type
        pytest.fail(
            "Redis is not reachable. Start it with "
            "`docker compose up -d redis`, or point REDIS_URL at one. "
            f"Underlying error: {exc}"
        )
    return client


@pytest.fixture
def job_id(redis_client):
    """A unique job id, with every key it could own deleted afterwards."""
    new_id = f"test-{uuid.uuid4().hex[:12]}"
    yield new_id
    for key in redis_client.scan_iter(match=f"orthonym:job:{new_id}*"):
        redis_client.delete(key)


@pytest.fixture(autouse=True)
def eager_celery_by_default():
    """Every naming endpoint now runs its OPSIN work on a Celery task via
    apply_async(...).get(timeout=...). Without eager mode that publishes to
    the real broker and blocks waiting for a worker that is never running
    during the test suite, so this defaults every test to eager execution.

    tests/test_jobs_api.py and tests/test_fast_path.py already flip this
    themselves (harmless to set twice); this is what keeps tests/test_api.py
    working too -- it predates the queue, calls /api/explain and
    /api/explain-name over HTTP, and has no eager fixture of its own.
    """
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    yield
    celery_app.conf.task_always_eager = False
    celery_app.conf.task_eager_propagates = False


@pytest.fixture(autouse=True)
def _reset_rate_limit_state():
    """Clear every per-IP rate-limit key before each test.

    fastapi.testclient.TestClient always reports the same client host
    ("testclient"), so the concurrent-job cap and the hourly/per-minute
    counters would otherwise accumulate across the WHOLE suite instead of
    resetting per test -- most visibly in tests/test_jobs_api.py, which
    submits jobs via POST /api/jobs without always polling
    GET /api/jobs/{id} (the thing that releases the concurrent-job slot),
    so a handful of tests would exhaust RATE_LIMIT_MAX_CONCURRENT_JOBS and
    every later job submission in the suite would 429.
    """
    from app.redis_store import get_redis

    client = get_redis()
    for key in client.scan_iter(match="orthonym:ip:*"):
        client.delete(key)
    yield


@pytest.fixture(autouse=True)
def pretend_a_worker_has_opsin():
    """Eager Celery never fires worker_process_init, so no worker ever
    reports its JVM and every naming endpoint would 503. Stand in for one.

    Unconditional (not gated on a test requesting `redis_client`): naming
    endpoints are reachable from any test file that imports app.main
    (tests/test_api.py included), and Redis is guaranteed available for the
    whole suite (see scripts/run-tests.sh), so there is no test for which
    skipping this would be correct.
    """
    from app.redis_store import get_redis, record_worker_opsin_status

    record_worker_opsin_status(999999, ok=True)
    yield
    get_redis().delete("orthonym:worker:999999:opsin")


@pytest.fixture
def no_worker_opsin(pretend_a_worker_has_opsin):
    """Opt out of the default healthy-worker fake, for a test that asserts
    the fail-closed 503 path. Depends on pretend_a_worker_has_opsin
    explicitly (rather than racing an unordered autouse fixture) so pytest
    runs that fixture's setup -- which writes the 999999 key -- first, and
    this deletes it afterwards. Also clears any other worker key a
    different test may have left, so "no worker" really means none.
    """
    from app.redis_store import get_redis

    client = get_redis()
    for key in client.scan_iter(match="orthonym:worker:*:opsin"):
        client.delete(key)
    yield
