"""Every Redis key Orthonym uses, and nothing else.

One module owns the key strings so a rename is a single edit and no caller
can invent a key that misses its TTL. Job results are deliberately
transient: the no-database rule in CLAUDE.md means Redis is the only store,
so an untagged key would grow without bound.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Iterator

import redis

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_KEY_PREFIX = "orthonym"
# Long enough that a worker restart is visible within a poll or two, short
# enough that a dead worker's "ok" cannot linger and make health lie.
_WORKER_STATUS_TTL = 120

_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    """One connection pool per process. decode_responses keeps callers free
    of bytes/str juggling; every value we store is JSON or a short string.
    """
    global _client
    if _client is None:
        _client = redis.Redis.from_url(
            get_settings().REDIS_URL, decode_responses=True
        )
    return _client


def job_meta_key(job_id: str) -> str:
    return f"{_KEY_PREFIX}:job:{job_id}:meta"


def job_rows_key(job_id: str) -> str:
    return f"{_KEY_PREFIX}:job:{job_id}:rows"


def job_chunk_key(job_id: str, index: int) -> str:
    return f"{_KEY_PREFIX}:job:{job_id}:chunk:{index}"


def _worker_key(pid: int) -> str:
    return f"{_KEY_PREFIX}:worker:{pid}:opsin"


def create_job(job_id: str, total: int, fmt: str, client_ip: str) -> None:
    settings = get_settings()
    client = get_redis()
    key = job_meta_key(job_id)
    now = int(time.time())
    pipe = client.pipeline()
    pipe.hset(
        key,
        mapping={
            "status": "queued",
            "total": total,
            "done": 0,
            "failed": 0,
            "created": now,
            "expires": now + settings.JOB_RESULT_TTL_SECONDS,
            "fmt": fmt,
            "ip": client_ip,
        },
    )
    pipe.expire(key, settings.JOB_RESULT_TTL_SECONDS)
    pipe.execute()


def _retag_if_untagged(pipe, key: str) -> None:
    """Give `key` a TTL if and only if it currently has none.

    HSET and HINCRBY recreate a missing hash, and the recreated key has NO
    expiry -- the unbounded-growth failure this module exists to prevent. The
    key can go missing at any moment, not just after its 24 hours: the Redis
    container runs `volatile-lru`, which makes every TTL-tagged key an
    eviction candidate under memory pressure regardless of remaining TTL.

    EXPIRE ... NX rather than a plain EXPIRE, because re-arming the full TTL
    on every progress bump would push a busy job's expiry past the
    `expires` timestamp create_job recorded and reports to callers as
    expires_at. NX touches only a key that lost its expiry, so a live TTL
    keeps counting down. Verified against Redis 7.4: NX returns 1 on an
    untagged key and 0 on a tagged one, leaving its TTL unchanged.
    """
    pipe.expire(key, get_settings().JOB_RESULT_TTL_SECONDS, nx=True)


def set_job_status(job_id: str, status: str) -> None:
    key = job_meta_key(job_id)
    pipe = get_redis().pipeline()
    pipe.hset(key, "status", status)
    _retag_if_untagged(pipe, key)
    pipe.execute()


def bump_job_done(job_id: str, done: int, failed: int) -> None:
    """Count molecules, not chunks, so progress moves smoothly."""
    client = get_redis()
    key = job_meta_key(job_id)
    pipe = client.pipeline()
    if done:
        pipe.hincrby(key, "done", done)
    if failed:
        pipe.hincrby(key, "failed", failed)
    _retag_if_untagged(pipe, key)
    pipe.execute()


def read_job_meta(job_id: str) -> dict[str, str] | None:
    meta = get_redis().hgetall(job_meta_key(job_id))
    return meta or None


def write_chunk(job_id: str, index: int, rows: list[dict]) -> None:
    """Each chunk owns its own key because chunks finish out of order;
    ordering is restored once, in assemble_rows.
    """
    settings = get_settings()
    client = get_redis()
    key = job_chunk_key(job_id, index)
    client.set(key, json.dumps(rows), ex=settings.JOB_RESULT_TTL_SECONDS)


def assemble_rows(job_id: str, n_chunks: int) -> int:
    """Concatenate the chunks in index order into the final row list, then
    delete the chunk keys. Returns the number of rows written.
    """
    settings = get_settings()
    client = get_redis()
    rows_key = job_rows_key(job_id)

    client.delete(rows_key)
    written = 0
    missing: list[int] = []
    for index in range(n_chunks):
        raw = client.get(job_chunk_key(job_id, index))
        if raw is None:
            # A chunk whose key expired or was never written. Skipping it
            # silently would let the job report "done" with rows missing,
            # which spec section 10 forbids -- so it is logged here, and
            # finalize_job compares the returned count against the job's
            # total and marks the job failed when they disagree.
            missing.append(index)
            continue
        rows = json.loads(raw)
        if rows:
            client.rpush(rows_key, *(json.dumps(r) for r in rows))
            written += len(rows)

    if missing:
        logger.error(
            "Job %s: %s of %s chunk keys were missing at assembly (indices "
            "%s). The result list is INCOMPLETE; finalize_job will mark the "
            "job failed.",
            job_id,
            len(missing),
            n_chunks,
            missing,
        )

    client.expire(rows_key, settings.JOB_RESULT_TTL_SECONDS)
    if n_chunks:
        # Redis rejects DEL with no keys, and a job with zero chunks is
        # reachable only through a caller bug -- but an exception here would
        # lose the rows already assembled above.
        client.delete(*(job_chunk_key(job_id, i) for i in range(n_chunks)))
    client.expire(job_meta_key(job_id), settings.JOB_RESULT_TTL_SECONDS)
    return written


def rows_length(job_id: str) -> int:
    """How many rows the job actually has. Used to tell an already-closed
    job from one that needs assembling, so a redelivered close is a no-op
    instead of wiping a finished job's results.
    """
    return int(get_redis().llen(job_rows_key(job_id)))


def read_rows(job_id: str, offset: int, limit: int) -> list[dict]:
    raw = get_redis().lrange(job_rows_key(job_id), offset, offset + limit - 1)
    return [json.loads(r) for r in raw]


def iter_all_rows(job_id: str, page: int = 500) -> Iterator[dict]:
    """Page through the whole result list, for CSV streaming. Never loads a
    10,000-row job into memory at once.
    """
    offset = 0
    while True:
        rows = read_rows(job_id, offset, page)
        if not rows:
            return
        yield from rows
        offset += len(rows)


def record_worker_opsin_status(pid: int, ok: bool) -> None:
    get_redis().set(
        _worker_key(pid), "ok" if ok else "failed", ex=_WORKER_STATUS_TTL
    )


def any_worker_has_opsin() -> bool:
    """True when at least one live worker reported a working JVM.

    False is what makes /api/health degrade and naming endpoints return 503
    rather than serving names whose tier nobody verified.
    """
    client = get_redis()
    for key in client.scan_iter(match=f"{_KEY_PREFIX}:worker:*:opsin"):
        if client.get(key) == "ok":
            return True
    return False
