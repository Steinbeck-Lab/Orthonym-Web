import pytest
from fastapi import HTTPException, Request

from app import ratelimit
from app.core.config import get_settings

IP = "203.0.113.7"


@pytest.fixture(autouse=True)
def clean_ip(redis_client):
    for key in redis_client.scan_iter(match=f"stitch:ip:{IP}*"):
        redis_client.delete(key)
    yield
    for key in redis_client.scan_iter(match=f"stitch:ip:{IP}*"):
        redis_client.delete(key)


def _request(headers: dict[str, str], host: str = "10.0.0.1") -> Request:
    scope = {
        "type": "http",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "client": (host, 12345),
    }
    return Request(scope)


def test_client_ip_ignores_forwarded_header_by_default(monkeypatch):
    # X-Forwarded-For is attacker-controlled. Trusting it unconditionally
    # makes every per-IP cap bypassable with one header.
    monkeypatch.setattr(get_settings(), "TRUST_PROXY_HEADERS", False, raising=False)
    request = _request({"x-forwarded-for": "1.1.1.1"}, host="10.0.0.1")
    assert ratelimit.client_ip(request) == "10.0.0.1"


def test_client_ip_uses_first_forwarded_hop_when_trusted(monkeypatch):
    monkeypatch.setattr(get_settings(), "TRUST_PROXY_HEADERS", True, raising=False)
    request = _request({"x-forwarded-for": "1.1.1.1, 10.0.0.2"})
    assert ratelimit.client_ip(request) == "1.1.1.1"


def test_concurrent_job_cap(monkeypatch):
    monkeypatch.setattr(
        get_settings(), "RATE_LIMIT_MAX_CONCURRENT_JOBS", 2, raising=False
    )
    ratelimit.check_job_allowed(IP)
    ratelimit.register_job(IP, "job-a")
    ratelimit.check_job_allowed(IP)
    ratelimit.register_job(IP, "job-b")

    with pytest.raises(HTTPException) as excinfo:
        ratelimit.check_job_allowed(IP)
    assert excinfo.value.status_code == 429
    assert "2" in excinfo.value.detail


def test_releasing_a_job_frees_the_slot(monkeypatch):
    monkeypatch.setattr(
        get_settings(), "RATE_LIMIT_MAX_CONCURRENT_JOBS", 1, raising=False
    )
    ratelimit.register_job(IP, "job-a")
    with pytest.raises(HTTPException):
        ratelimit.check_job_allowed(IP)
    ratelimit.release_job(IP, "job-a")
    ratelimit.check_job_allowed(IP)  # must not raise


def test_hourly_job_cap(monkeypatch):
    monkeypatch.setattr(
        get_settings(), "RATE_LIMIT_JOBS_PER_HOUR", 3, raising=False
    )
    monkeypatch.setattr(
        get_settings(), "RATE_LIMIT_MAX_CONCURRENT_JOBS", 100, raising=False
    )
    for _ in range(3):
        ratelimit.check_job_allowed(IP)
    with pytest.raises(HTTPException) as excinfo:
        ratelimit.check_job_allowed(IP)
    assert excinfo.value.status_code == 429
    assert "hour" in excinfo.value.detail.lower()


def test_fast_path_has_its_own_cap(monkeypatch):
    # The job caps do not cover /api/translate, so without this a script can
    # hammer the fast queue freely.
    monkeypatch.setattr(
        get_settings(), "RATE_LIMIT_FAST_PER_MINUTE", 2, raising=False
    )
    ratelimit.check_fast_allowed(IP)
    ratelimit.check_fast_allowed(IP)
    with pytest.raises(HTTPException) as excinfo:
        ratelimit.check_fast_allowed(IP)
    assert excinfo.value.status_code == 429


def test_counter_keys_carry_a_ttl(redis_client, monkeypatch):
    monkeypatch.setattr(
        get_settings(), "RATE_LIMIT_JOBS_PER_HOUR", 100, raising=False
    )
    ratelimit.check_job_allowed(IP)
    keys = list(redis_client.scan_iter(match=f"stitch:ip:{IP}:hour:*"))
    assert keys, "hourly counter was never written"
    # A counter without a TTL would ban an IP forever.
    assert all(redis_client.ttl(k) > 0 for k in keys)
