"""Per-IP caps. STITCH has no accounts, so this is the only thing between a
public queue and one script filling it.

Deliberately crude: two counters and a set. Anything more would need
identity, and identity means accounts, which CLAUDE.md rules out.
"""

from __future__ import annotations

import time

from fastapi import HTTPException, Request

from app.core.config import get_settings
from app.redis_store import get_redis

_HOUR = 3600
_MINUTE = 60


def client_ip(request: Request) -> str:
    """The caller's address.

    X-Forwarded-For is set by the client unless a reverse proxy overwrites
    it, so trusting it by default would make every cap here bypassable with
    one header. It is honoured only when the operator says a trusted proxy
    is in front (TRUST_PROXY_HEADERS).
    """
    settings = get_settings()
    if settings.TRUST_PROXY_HEADERS:
        forwarded = request.headers.get("x-forwarded-for", "")
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    return request.client.host if request.client else "unknown"


def _jobs_key(ip: str) -> str:
    return f"stitch:ip:{ip}:jobs"


def _hour_key(ip: str) -> str:
    return f"stitch:ip:{ip}:hour:{int(time.time()) // _HOUR}"


def _minute_key(ip: str) -> str:
    return f"stitch:ip:{ip}:minute:{int(time.time()) // _MINUTE}"


def check_job_allowed(ip: str) -> None:
    settings = get_settings()
    client = get_redis()

    active = client.scard(_jobs_key(ip))
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


def register_job(ip: str, job_id: str) -> None:
    client = get_redis()
    key = _jobs_key(ip)
    client.sadd(key, job_id)
    # Bound the set even if a release is ever missed, so a crashed job
    # cannot occupy a slot forever.
    client.expire(key, get_settings().JOB_RESULT_TTL_SECONDS)


def release_job(ip: str, job_id: str) -> None:
    get_redis().srem(_jobs_key(ip), job_id)
