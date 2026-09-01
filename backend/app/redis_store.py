"""Every Redis key Orthonym uses, and nothing else.

One module owns the key strings so a rename is a single edit and no caller
can invent a key that misses its TTL. Job results are deliberately
transient: the no-database rule in CLAUDE.md means Redis is the only store,
so an untagged key would grow without bound.

ONE deliberate exception, stated here so nobody "fixes" it: the worker
registry `orthonym:workers:opsin` carries NO key-level TTL at all
(record_worker_opsin_status prunes stale FIELDS instead). That is correct and
load-bearing -- Redis runs with volatile-lru, which can only evict keys that
HAVE an expiry, so giving this one a TTL would make the worker registry
evictable and recreate the outage where every naming endpoint 503s because no
worker appears to exist. Audit item CC3-workers-key-ttl-docstring: the
invariant above, read literally, invites exactly that change.
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


# ONE hash, field = worker pid, value = "ok:<unix ts>" / "failed:<unix ts>".
# Round 3 review, finding 3: a distinct "orthonym:worker:{pid}:opsin" key per
# worker made any_worker_has_opsin() scan_iter() the WHOLE keyspace on
# every naming request and on GET /api/health (which has no rate limiter
# at all) -- measured at 0.372 s over 200,000 keys, an ordinary size once
# a 7-day name cache and 10,000-row jobs are in the mix. A single hash
# makes both record and read O(number of workers), never O(keyspace size).
_WORKERS_HASH_KEY = f"{_KEY_PREFIX}:workers:opsin"


def ip_jobs_key(ip: str) -> str:
    """The per-IP concurrent-job set. Owned here, not app.ratelimit, so
    Celery worker code (app.tasks) can release a slot via remove_ip_job
    below without importing app.ratelimit -- which imports fastapi for its
    HTTPException-raising checks, a dependency worker code should not need.
    """
    return f"{_KEY_PREFIX}:ip:{ip}:jobs"


def remove_ip_job(ip: str, job_id: str) -> None:
    """Bare srem primitive: drop `job_id` from the per-IP concurrent-job
    set. Called both from app.ratelimit.release_job (the HTTP-facing name)
    and directly from app.tasks (_close_job, mark_job_failed), which must
    not import fastapi just to free a slot.
    """
    get_redis().srem(ip_jobs_key(ip), job_id)


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


# KEYS[1] = the job's meta hash (job_meta_key).
# ARGV[1] = TTL seconds to arm on the hash -- only if it has none (NX), same
#           reasoning as _retag_if_untagged: re-arming the full TTL on every
#           chunk would push a busy job's expiry past what create_job
#           recorded and reports as expires_at.
#
# Mirrors app.ratelimit._ADMIT_JOB_SCRIPT: one round trip, so a redelivered
# chunk racing a real one cannot both read "not yet terminal" and both
# proceed to reopen a job that a moment ago legitimately finished.
_BEGIN_CHUNK_SCRIPT = """
local status = redis.call('HGET', KEYS[1], 'status')
if status == 'done' or status == 'failed' then
    return 0
end
redis.call('HSET', KEYS[1], 'status', 'running')
redis.call('EXPIRE', KEYS[1], ARGV[1], 'NX')
return 1
"""

_begin_chunk_script_obj = None


def _begin_chunk_script():
    global _begin_chunk_script_obj
    if _begin_chunk_script_obj is None:
        _begin_chunk_script_obj = get_redis().register_script(_BEGIN_CHUNK_SCRIPT)
    return _begin_chunk_script_obj


def begin_chunk(job_id: str) -> bool:
    """Atomically move a job to "running" for one more chunk, UNLESS it is
    already terminal ("done"/"failed").

    task_acks_late=True (celery_app.py) makes chunk redelivery real: a
    chunk whose ack was lost after it finished, or whose worker died just
    after finishing, comes back and runs again. Without this guard,
    run_chunk's bare set_job_status(job_id, "running") would flip an
    already-closed job back to "running" forever -- the chord body has
    already fired once and Celery will not fire it again, so nothing would
    ever close the job a second time (final review report, I1). Returning
    False also lets run_chunk skip the pointless re-naming of a whole
    chunk that already has rows.

    This does not by itself stop the progress counter from double-counting
    a chunk redelivered BEFORE the job closes -- see bump_job_done's own
    per-chunk marker for that half.
    """
    key = job_meta_key(job_id)
    settings = get_settings()
    result = _begin_chunk_script()(
        keys=[key], args=[settings.JOB_RESULT_TTL_SECONDS]
    )
    return bool(result)


def bump_job_done(job_id: str, index: int, done: int, failed: int) -> None:
    """Count molecules, not chunks, so progress moves smoothly.

    Idempotent per chunk: HSETNX on a `bumped:{index}` marker field in the
    same meta hash gates the HINCRBY calls below, so a chunk redelivered by
    task_acks_late=True (celery_app.py) cannot double-count molecules it
    already counted the first time it ran (final review report, I1;
    measured there: one redelivered 25-molecule chunk of a 50-molecule job
    pushed `done` to 75). HSETNX is atomic, so two concurrent redeliveries
    of the SAME chunk cannot both win the race and both proceed.
    """
    client = get_redis()
    key = job_meta_key(job_id)
    if not client.hsetnx(key, f"bumped:{index}", 1):
        return
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
    # nx=True, matching _retag_if_untagged and _BEGIN_CHUNK_SCRIPT (deferred
    # item 3). A plain EXPIRE here restarted the 24 hours from the moment the
    # job closed, so the real expiry drifted past the absolute `expires` that
    # create_job recorded and GET /api/jobs/{id} already reported as
    # expires_at -- by roughly the job's runtime, which on a long batch is
    # hours. NX re-arms the key only if it somehow lost its TTL, which is the
    # case this call exists for.
    client.expire(job_meta_key(job_id), settings.JOB_RESULT_TTL_SECONDS, nx=True)
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
    """Record this worker's status in the shared hash, carrying its own
    timestamp (there is no per-FIELD TTL in Redis, only per-KEY), and prune
    any field that has aged out past _WORKER_STATUS_TTL -- including this
    one, if `ok` somehow arrives already stale, and every OTHER worker's
    entry too. Pruning here, on every write, is what keeps the hash from
    growing across worker restarts over a long-running deployment: as long
    as at least one worker writes periodically, the hash never holds more
    than the currently-live pids.
    """
    client = get_redis()
    key = _WORKERS_HASH_KEY
    now = int(time.time())
    client.hset(key, str(pid), f"{'ok' if ok else 'failed'}:{now}")

    stale = []
    for field, value in client.hgetall(key).items():
        status_ts = value.rsplit(":", 1)
        if len(status_ts) != 2 or not status_ts[1].isdigit():
            stale.append(field)  # malformed -- cannot be trusted either way
            continue
        if now - int(status_ts[1]) > _WORKER_STATUS_TTL:
            stale.append(field)
    if stale:
        client.hdel(key, *stale)


def any_worker_has_opsin() -> bool:
    """True when at least one live worker reported a working JVM within
    the last _WORKER_STATUS_TTL seconds.

    False is what makes /api/health degrade and naming endpoints return 503
    rather than serving names whose tier nobody verified. A single HGETALL
    -- never a keyspace scan -- so this stays cheap regardless of how many
    OTHER keys (name cache entries, job rows) Redis is holding.
    """
    client = get_redis()
    now = int(time.time())
    for value in client.hgetall(_WORKERS_HASH_KEY).values():
        status_ts = value.rsplit(":", 1)
        if len(status_ts) != 2 or not status_ts[1].isdigit():
            continue
        status, ts = status_ts
        if status == "ok" and now - int(ts) <= _WORKER_STATUS_TTL:
            return True
    return False
