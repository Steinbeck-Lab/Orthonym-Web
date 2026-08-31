"""Shared fixtures. GOLDEN_NAMES is the fixed decomposition corpus every
later task asserts against; add to it, never reorder or remove entries.
"""

import uuid

import pytest

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
    for key in redis_client.scan_iter(match=f"stitch:job:{new_id}*"):
        redis_client.delete(key)
