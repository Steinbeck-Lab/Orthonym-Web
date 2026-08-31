"""Per-IP caps. Orthonym has no accounts, so this is the only thing between a
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
# the next admission call from that IP cleans them up itself.
#
# One round trip, so N simultaneous submissions from one IP cannot all read
# the same pre-admission count and all pass the cap (round 1 review,
# Critical 2 / TOCTOU).
#
# The literal 'orthonym:job:' / ':meta' below must track
# app.redis_store.job_meta_key's format -- pinned by
# tests/test_redis_keys.py::test_keys_are_namespaced_and_stable, so a
# rename there is caught immediately rather than silently breaking this.
_ADMIT_JOB_SCRIPT = """
local members = redis.call('SMEMBERS', KEYS[1])
for _, jid in ipairs(members) do
    local status = redis.call('HGET', 'orthonym:job:' .. jid .. ':meta', 'status')
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
    otherwise be 2**64 free buckets for the same client.
    """
    try:
        parsed = ipaddress.ip_address(raw)
    except ValueError:
        return None
    if isinstance(parsed, ipaddress.IPv6Address):
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
        for hop in reversed(hops):
            bucketed = _bucket(hop)
            if bucketed:
                return bucketed

    return request.client.host if request.client else "unknown"


def _hour_key(ip: str) -> str:
    return f"orthonym:ip:{ip}:hour:{int(time.time()) // _HOUR}"


def _minute_key(ip: str) -> str:
    return f"orthonym:ip:{ip}:minute:{int(time.time()) // _MINUTE}"


def _depict_minute_key(ip: str) -> str:
    return f"orthonym:ip:{ip}:depict:{int(time.time()) // _MINUTE}"


def check_job_allowed(ip: str) -> None:
    """A cheap, non-authoritative pre-check: reject an obviously-over-cap
    caller before the server reads or parses their submission at all
    (round 1 review, Important -- a 429'd caller had already made the
    server read up to 50 MB and RDKit-parse up to 10,000 molecules).

    check_and_register_job's atomic script, called right before a job is
    actually created and dispatched, is the one that actually enforces the
    cap; a caller that races past this cheap check is still caught there.
    """
    settings = get_settings()
    client = get_redis()

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
    """The authoritative gate: atomically self-heal, count, and register in
    one round trip, right before a job is actually created and dispatched.

    No code path may create-and-dispatch a job without going through this
    (round 1 review, Critical 2) -- see app.jobs_api.admit_and_dispatch,
    which both POST /api/jobs and POST /api/translate's over-the-fast-limit
    /ratelimit-timeout branches call.
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
    mechanism against a separate, much larger budget instead.
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
