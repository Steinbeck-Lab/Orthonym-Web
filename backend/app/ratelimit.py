"""Per-IP caps. STITCH has no accounts, so this is the only thing between a
public queue and one script filling it.

Deliberately crude: two counters and one set. Anything more would need
identity, and identity means accounts, which CLAUDE.md rules out.
"""

from __future__ import annotations

import ipaddress
import time

from fastapi import HTTPException, Request

from app.core.config import get_settings
from app.redis_store import get_redis, ip_jobs_key, remove_ip_job

_HOUR = 3600
_MINUTE = 60

# KEYS[1] = the per-IP concurrent-jobs set (app.redis_store.ip_jobs_key).
# ARGV[1] = job id to admit, or "" to self-heal-and-count only (no write).
# ARGV[2] = concurrent-job cap.
# ARGV[3] = TTL seconds to arm on the set -- only if it has none (NX).
#           Refreshing it on every admission would keep a leaked slot's set
#           alive forever (round 1 review, Important: "register_job
#           re-expires the whole set on every sadd").
#
# Self-heals first: a member whose job has already finished, or whose meta
# already aged out, is dropped before counting. This is what makes it safe
# for _close_job/mark_job_failed to skip releasing in the cases they
# cannot reach at all (no ip on hand, no errback, a hard-limit SIGKILL) --
# the next admission call from that IP cleans them up itself. One
# consequence this does NOT try to fix (round 2 review): if the Redis
# container's volatile-lru evicts a RUNNING job's meta under memory
# pressure, the next admission reads that the same way it reads a
# genuinely finished job -- as absent -- and frees the slot early. Rare,
# and the alternative (never self-healing on absence) reintroduces the
# permanent leak this exists to prevent, so it is accepted rather than
# solved.
#
# One round trip, so N simultaneous submissions from one IP cannot all read
# the same pre-admission count and all pass the cap (round 1 review,
# Critical 2 / TOCTOU).
#
# The literal 'stitch:job:' / ':meta' below must track
# app.redis_store.job_meta_key's format -- pinned by
# tests/test_redis_keys.py::test_keys_are_namespaced_and_stable, so a
# rename there is caught immediately rather than silently breaking this.
_ADMIT_JOB_SCRIPT = """
local members = redis.call('SMEMBERS', KEYS[1])
for _, jid in ipairs(members) do
    local status = redis.call('HGET', 'stitch:job:' .. jid .. ':meta', 'status')
    if (status == false) or (status == 'done') or (status == 'failed') then
        redis.call('SREM', KEYS[1], jid)
    end
end
local active = redis.call('SCARD', KEYS[1])
if ARGV[1] == '' then
    return active
end
local cap = tonumber(ARGV[2])
if active >= cap then
    return active
end
redis.call('SADD', KEYS[1], ARGV[1])
redis.call('EXPIRE', KEYS[1], ARGV[3], 'NX')
return -1
"""

_admit_job_script_obj = None


def _admit_job_script():
    """Lazily register the Lua script against the current Redis connection.

    Deferred, not module-scope, so importing this module never needs a
    live Redis connection -- only the first actual admission call does.
    """
    global _admit_job_script_obj
    if _admit_job_script_obj is None:
        _admit_job_script_obj = get_redis().register_script(_ADMIT_JOB_SCRIPT)
    return _admit_job_script_obj


def _bucket(raw: str) -> str | None:
    """Validate `raw` as an IP address and return the Redis-key bucket for
    it, or None if it does not parse.

    The value becomes part of a Redis key, so attacker-supplied header text
    must never reach it unvalidated. IPv6 is bucketed by /64 -- a single
    routed allocation -- not /128: one address per rotating /64 would
    otherwise be 2**64 free buckets for the same client. An IPv4-mapped
    IPv6 address (::ffff:a.b.c.d) is normalised to its plain IPv4 form
    FIRST: bucketing it as IPv6 instead would apply /64 to an address
    whose first 64 bits are always the same fixed prefix, so EVERY mapped
    address (and, per the round 2 review's measurement, an address like
    ::1 that shares that same all-zero prefix) collapses onto one shared
    bucket regardless of the actual v4 address embedded in it.
    """
    try:
        parsed = ipaddress.ip_address(raw)
    except ValueError:
        return None
    if isinstance(parsed, ipaddress.IPv6Address):
        mapped = parsed.ipv4_mapped
        if mapped is not None:
            return str(mapped)
        network = ipaddress.ip_network(f"{parsed}/64", strict=False)
        return str(network.network_address)
    return str(parsed)


def client_ip(request: Request) -> str:
    """The caller's address, ready to use as a Redis key.

    Proxy headers are consulted only when TRUST_PROXY_HEADERS says a
    reverse proxy is in front -- they are otherwise entirely
    attacker-controlled. Even then, X-Forwarded-For's LEFTMOST hop is
    still attacker text: nginx.conf sets it to
    $proxy_add_x_forwarded_for, which APPENDS $remote_addr to whatever the
    client already sent, so only the RIGHTMOST hop (nginx's own immediate
    peer) is trustworthy. X-Real-IP ($remote_addr verbatim) is preferred
    first when present, since it carries no attacker-supplied prefix at
    all. (Round 1 review, Critical 3: the previous version read the
    leftmost XFF hop and ignored X-Real-IP entirely -- exactly backwards.)

    Only the RIGHTMOST hop is ever consulted -- not a walk further left
    looking for the first hop that happens to parse. Round 2 review: a
    header like "1.2.3.4, junk" used to have the loop skip over the
    unparseable rightmost hop and fall through to "1.2.3.4", which is
    attacker-supplied text sitting to ITS left. If the one hop that is
    actually trustworthy does not parse, the honest move is to fall back
    to the TCP peer, not to keep searching left through text the client
    controls.
    """
    settings = get_settings()
    if settings.TRUST_PROXY_HEADERS:
        real_ip = request.headers.get("x-real-ip", "").strip()
        if real_ip:
            bucketed = _bucket(real_ip)
            if bucketed:
                return bucketed

        forwarded = request.headers.get("x-forwarded-for", "")
        hops = [hop.strip() for hop in forwarded.split(",") if hop.strip()]
        if hops:
            bucketed = _bucket(hops[-1])
            if bucketed:
                return bucketed

    return request.client.host if request.client else "unknown"


def _hour_key(ip: str) -> str:
    return f"stitch:ip:{ip}:hour:{int(time.time()) // _HOUR}"


def _minute_key(ip: str) -> str:
    return f"stitch:ip:{ip}:minute:{int(time.time()) // _MINUTE}"


def _depict_minute_key(ip: str) -> str:
    return f"stitch:ip:{ip}:depict:{int(time.time()) // _MINUTE}"


def _reject_if_concurrent_cap_exceeded(ip: str) -> None:
    settings = get_settings()
    active = _admit_job_script()(
        keys=[ip_jobs_key(ip)],
        args=[
            "",
            settings.RATE_LIMIT_MAX_CONCURRENT_JOBS,
            settings.JOB_RESULT_TTL_SECONDS,
        ],
    )
    if active >= settings.RATE_LIMIT_MAX_CONCURRENT_JOBS:
        raise HTTPException(
            status_code=429,
            detail=(
                f"You already have {active} jobs running, and the limit is "
                f"{settings.RATE_LIMIT_MAX_CONCURRENT_JOBS}. Wait for one to "
                "finish, or delete it."
            ),
        )


def check_concurrent_cap_only(ip: str) -> None:
    """A cheap, early, non-authoritative pre-check: reject an obviously-
    over-cap caller before the server reads or parses their submission at
    all (round 1 review, Important -- a 429'd caller had already made the
    server read up to 50 MB and RDKit-parse up to 10,000 molecules).

    Concurrent cap only, and deliberately does NOT touch the hourly
    counter -- check_job_allowed (below) is where that is counted, exactly
    once per admission, from app.jobs_api.admit_and_dispatch. Calling
    check_job_allowed here TOO, as an earlier version of this pre-check
    did, would charge the hourly cap twice for every POST /api/jobs
    submission while /api/translate's job branch (which never called this
    pre-check at all) charged it zero times -- which is exactly the round
    2 review's finding 1.
    """
    _reject_if_concurrent_cap_exceeded(ip)


def check_job_allowed(ip: str) -> None:
    """The admission gate: concurrent cap (a cheap self-healing dry-run)
    AND the hourly cap, together. Called exactly once per admission, from
    app.jobs_api.admit_and_dispatch -- both POST /api/jobs and
    POST /api/translate's job-dispatch branches go through
    admit_and_dispatch, so this now applies uniformly to both (round 2
    review, finding 1: only POST /api/jobs used to call this, so
    RATE_LIMIT_JOBS_PER_HOUR did not exist at all on the envelope path --
    measured at 30 jobs of up to 10,000 molecules each in 30 requests,
    where POST /api/jobs would have 429'd after 3).

    Not itself the TOCTOU-safe registration step -- check_and_register_job
    is. The hourly counter does not need the same Lua treatment: a bare
    INCR is already atomic, so there is no separate check-then-write race
    to close for it the way there was for the concurrent-job set.
    """
    _reject_if_concurrent_cap_exceeded(ip)

    settings = get_settings()
    client = get_redis()
    key = _hour_key(ip)
    count = client.incr(key)
    if count == 1:
        # Set the TTL only on creation: refreshing it on every hit would
        # extend the window forever and never let the counter reset.
        client.expire(key, _HOUR)
    if count > settings.RATE_LIMIT_JOBS_PER_HOUR:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Limit of {settings.RATE_LIMIT_JOBS_PER_HOUR} jobs per hour "
                f"reached. Resets in {client.ttl(key)} seconds."
            ),
        )


def check_and_register_job(ip: str, job_id: str) -> None:
    """The TOCTOU-safe registration step: atomically self-heal, count, and
    register in one round trip, right before a job is actually created and
    dispatched.

    No code path may create-and-dispatch a job without going through this
    (round 1 review, Critical 2) -- see app.jobs_api.admit_and_dispatch,
    which both POST /api/jobs and POST /api/translate's over-the-fast-limit
    /ratelimit-timeout branches call. admit_and_dispatch also calls
    check_job_allowed (above) for the hourly cap, which this does not
    itself enforce.
    """
    settings = get_settings()
    result = _admit_job_script()(
        keys=[ip_jobs_key(ip)],
        args=[
            job_id,
            settings.RATE_LIMIT_MAX_CONCURRENT_JOBS,
            settings.JOB_RESULT_TTL_SECONDS,
        ],
    )
    if result != -1:
        raise HTTPException(
            status_code=429,
            detail=(
                f"You already have {result} jobs running, and the limit is "
                f"{settings.RATE_LIMIT_MAX_CONCURRENT_JOBS}. Wait for one to "
                "finish, or delete it."
            ),
        )


def check_fast_allowed(ip: str) -> None:
    settings = get_settings()
    client = get_redis()
    key = _minute_key(ip)
    count = client.incr(key)
    if count == 1:
        client.expire(key, _MINUTE)
    if count > settings.RATE_LIMIT_FAST_PER_MINUTE:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Limit of {settings.RATE_LIMIT_FAST_PER_MINUTE} requests per "
                f"minute reached. Resets in {client.ttl(key)} seconds."
            ),
        )


def check_depict_allowed(ip: str) -> None:
    """/api/depict is called once per visible row in a batch results table
    -- a legitimate 1,000-row view is 1,000 calls well within a minute.
    check_fast_allowed's budget (60/minute, sized for a single OPSIN
    lookup) would treat ordinary use as abuse, so this is the same
    mechanism against a separate, much larger budget instead. This is a
    request-count throttle, not a cost bound -- see jobs_api.MAX_DEPICT_ATOMS
    for the latter, which is what actually keeps one call cheap.
    """
    settings = get_settings()
    client = get_redis()
    key = _depict_minute_key(ip)
    count = client.incr(key)
    if count == 1:
        client.expire(key, _MINUTE)
    if count > settings.RATE_LIMIT_DEPICT_PER_MINUTE:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Limit of {settings.RATE_LIMIT_DEPICT_PER_MINUTE} "
                f"depictions per minute reached. Resets in "
                f"{client.ttl(key)} seconds."
            ),
        )


def release_job(ip: str, job_id: str) -> None:
    """HTTP-facing release. Delegates to app.redis_store's bare primitive
    so Celery worker code (app.tasks) can release a slot too without
    importing fastapi just for that.
    """
    remove_ip_job(ip, job_id)
