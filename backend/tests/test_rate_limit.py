import pytest
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient

from app import ratelimit, redis_store
from app.core.config import get_settings

IP = "203.0.113.7"


def _clean(redis_client) -> None:
    for key in redis_client.scan_iter(match=f"orthonym:ip:{IP}*"):
        redis_client.delete(key)
    # This file's tests create real job-meta hashes (via _admit /
    # test_a_finished_jobs_meta_self_heals_...) so check_and_register_job's
    # self-heal has something real to look at -- clean those up too rather
    # than leaving them to their 24h TTL.
    for key in redis_client.scan_iter(match="orthonym:job:job-*:meta"):
        redis_client.delete(key)
    redis_client.delete("orthonym:job:stale-job:meta")


@pytest.fixture(autouse=True)
def clean_ip(redis_client):
    _clean(redis_client)
    yield
    _clean(redis_client)


def _request(headers: dict[str, str], host: str = "10.0.0.1") -> Request:
    scope = {
        "type": "http",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "client": (host, 12345),
    }
    return Request(scope)


def _admit(ip: str, job_id: str) -> None:
    """Mirror app.jobs_api.admit_and_dispatch's real sequencing: job meta
    exists (status "queued", non-terminal) BEFORE the atomic admission call.

    check_and_register_job's self-heal treats a member with NO meta at all
    the same as one whose meta has long since expired -- correct in
    production, where admit_and_dispatch always creates meta first, but
    calling it standalone on a job with no meta at all would exercise that
    self-heal path instead of the cap these tests are actually about.
    """
    redis_store.create_job(job_id, total=1, fmt="smiles_list", client_ip=ip)
    ratelimit.check_and_register_job(ip, job_id)


def test_client_ip_ignores_forwarded_header_by_default(monkeypatch):
    # X-Forwarded-For is attacker-controlled. Trusting it unconditionally
    # makes every per-IP cap bypassable with one header.
    monkeypatch.setattr(get_settings(), "TRUST_PROXY_HEADERS", False, raising=False)
    request = _request({"x-forwarded-for": "1.1.1.1"}, host="10.0.0.1")
    assert ratelimit.client_ip(request) == "10.0.0.1"


def test_client_ip_prefers_x_real_ip_when_trusted(monkeypatch):
    # nginx.conf sets X-Real-IP to $remote_addr verbatim -- the one header
    # here that carries no attacker-supplied prefix at all.
    monkeypatch.setattr(get_settings(), "TRUST_PROXY_HEADERS", True, raising=False)
    request = _request(
        {"x-real-ip": "9.9.9.9", "x-forwarded-for": "1.1.1.1, 10.0.0.2"}
    )
    assert ratelimit.client_ip(request) == "9.9.9.9"


def test_client_ip_uses_the_rightmost_forwarded_hop_when_trusted(monkeypatch):
    # nginx.conf sets X-Forwarded-For to $proxy_add_x_forwarded_for, which
    # APPENDS $remote_addr to whatever the client already sent -- so the
    # rightmost hop is nginx's own immediate peer, the one hop in this
    # header a client cannot forge. The leftmost value is attacker text
    # (round 1 review, Critical 3 -- this test used to enshrine reading
    # the leftmost hop, which is exactly backwards).
    monkeypatch.setattr(get_settings(), "TRUST_PROXY_HEADERS", True, raising=False)
    request = _request({"x-forwarded-for": "1.1.1.1, 10.0.0.2"})
    assert ratelimit.client_ip(request) == "10.0.0.2"


def test_a_spoofed_multi_hop_header_cannot_pick_a_bucket(monkeypatch):
    # An attacker who controls X-Forwarded-For can pad it with as many fake
    # hops as they like; none of them may end up chosen over the
    # trustworthy value nginx itself appended on the right.
    monkeypatch.setattr(get_settings(), "TRUST_PROXY_HEADERS", True, raising=False)
    request = _request(
        {"x-forwarded-for": "9.9.9.9, 8.8.8.8, not-an-ip, 203.0.113.50"},
        host="10.0.0.9",
    )
    assert ratelimit.client_ip(request) == "203.0.113.50"


def test_an_unparseable_forwarded_header_falls_back_to_the_tcp_peer(monkeypatch):
    monkeypatch.setattr(get_settings(), "TRUST_PROXY_HEADERS", True, raising=False)
    request = _request({"x-forwarded-for": "not-an-ip-at-all"}, host="10.0.0.5")
    assert ratelimit.client_ip(request) == "10.0.0.5"


def test_ipv6_addresses_are_bucketed_by_slash_64(monkeypatch):
    # A routed /64 is a single allocation to one client; bucketing by /128
    # would give a rotating client 2**64 free buckets.
    monkeypatch.setattr(get_settings(), "TRUST_PROXY_HEADERS", True, raising=False)
    first = _request({"x-real-ip": "2001:db8:abcd:1234::1"})
    second = _request({"x-real-ip": "2001:db8:abcd:1234:ffff:ffff:ffff:ffff"})
    assert ratelimit.client_ip(first) == ratelimit.client_ip(second)
    assert ratelimit.client_ip(first) == "2001:db8:abcd:1234::"


def test_concurrent_job_cap(monkeypatch):
    monkeypatch.setattr(
        get_settings(), "RATE_LIMIT_MAX_CONCURRENT_JOBS", 2, raising=False
    )
    _admit(IP, "job-a")
    _admit(IP, "job-b")

    with pytest.raises(HTTPException) as excinfo:
        _admit(IP, "job-c")
    assert excinfo.value.status_code == 429
    assert "2" in excinfo.value.detail


def test_a_simultaneous_third_admission_still_cannot_pass_the_cap(monkeypatch):
    # The whole point of the Lua script: a separate SCARD-then-SADD lets N
    # simultaneous submissions all read the same pre-admission count and
    # all pass. This asserts the cap holds across repeated calls with no
    # gap for that race to land in.
    monkeypatch.setattr(
        get_settings(), "RATE_LIMIT_MAX_CONCURRENT_JOBS", 2, raising=False
    )
    admitted = 0
    rejected = 0
    for i in range(5):
        try:
            _admit(IP, f"job-{i}")
            admitted += 1
        except HTTPException:
            rejected += 1
    assert admitted == 2
    assert rejected == 3


def test_releasing_a_job_frees_the_slot(monkeypatch):
    monkeypatch.setattr(
        get_settings(), "RATE_LIMIT_MAX_CONCURRENT_JOBS", 1, raising=False
    )
    _admit(IP, "job-a")
    with pytest.raises(HTTPException):
        _admit(IP, "job-b")
    ratelimit.release_job(IP, "job-a")
    _admit(IP, "job-b")  # must not raise


def test_a_finished_jobs_meta_self_heals_the_slot_without_an_explicit_release(
    redis_client, monkeypatch
):
    # The leak classes an explicit release cannot reach: translate_job_inline
    # has no errback, _close_job's meta-missing branch has no ip to release
    # from, and a hard-time-limit SIGKILL runs neither. Self-healing at the
    # next admission is the safety net for exactly these.
    from app import redis_store

    monkeypatch.setattr(
        get_settings(), "RATE_LIMIT_MAX_CONCURRENT_JOBS", 1, raising=False
    )
    redis_store.create_job("stale-job", total=1, fmt="smiles_list", client_ip=IP)
    redis_client.sadd(f"orthonym:ip:{IP}:jobs", "stale-job")
    redis_store.set_job_status("stale-job", "done")

    # Without self-healing this would 429: the set already has one member
    # and the cap is 1.
    ratelimit.check_and_register_job(IP, "job-a")

    redis_client.delete(redis_store.job_meta_key("stale-job"))


def test_hourly_job_cap(monkeypatch):
    monkeypatch.setattr(
        get_settings(), "RATE_LIMIT_JOBS_PER_HOUR", 3, raising=False
    )
    monkeypatch.setattr(
        get_settings(), "RATE_LIMIT_MAX_CONCURRENT_JOBS", 100, raising=False
    )
    for i in range(3):
        ratelimit.check_job_allowed(IP)
        ratelimit.check_and_register_job(IP, f"job-{i}")
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
    keys = list(redis_client.scan_iter(match=f"orthonym:ip:{IP}:hour:*"))
    assert keys, "hourly counter was never written"
    # A counter without a TTL would ban an IP forever.
    assert all(redis_client.ttl(k) > 0 for k in keys)


def test_the_jobs_set_ttl_is_armed_once_not_refreshed_on_every_admission(
    redis_client, monkeypatch
):
    # register_job used to re-EXPIRE the whole set on every SADD, so an
    # active user's own leaked members would never age out. The set's TTL
    # must be armed once, on first creation, and never pushed back out.
    monkeypatch.setattr(
        get_settings(), "RATE_LIMIT_MAX_CONCURRENT_JOBS", 100, raising=False
    )
    monkeypatch.setattr(get_settings(), "JOB_RESULT_TTL_SECONDS", 1000, raising=False)
    _admit(IP, "job-a")
    key = f"orthonym:ip:{IP}:jobs"
    ttl_after_first = redis_client.ttl(key)
    assert ttl_after_first > 0

    redis_client.expire(key, 5)  # simulate most of the TTL having elapsed
    _admit(IP, "job-b")
    assert redis_client.ttl(key) <= 5, (
        "a second admission re-armed the full TTL instead of leaving the "
        "existing (shorter) one alone"
    )


def test_creating_jobs_over_http_enforces_the_concurrent_cap(
    redis_client, monkeypatch
):
    """End to end, over real HTTP: round 1 review, Critical 2 -- /api/jobs
    used to call check_job_allowed and register_job as two separate steps,
    and /api/translate's envelope branch called neither at all. A test
    that only calls app.ratelimit functions directly cannot catch either
    regression; this exercises the real endpoint.

    Eager Celery must be OFF for this one: in eager mode,
    translate_job_inline runs synchronously inside apply_async() itself and
    releases its own slot before this function returns, so a second
    submission would never be capped regardless of whether admission was
    ever checked at all -- which is exactly how a prior version of this
    round's fix passed vacuously.
    """
    from app.celery_app import celery_app
    from app.main import app

    monkeypatch.setattr(
        get_settings(), "RATE_LIMIT_MAX_CONCURRENT_JOBS", 1, raising=False
    )
    celery_app.conf.task_always_eager = False
    first_job_id = None
    try:
        client = TestClient(app)
        first = client.post("/api/jobs", json={"text": "CCO\n"})
        assert first.status_code == 200, first.text
        first_job_id = first.json()["job_id"]

        second = client.post("/api/jobs", json={"text": "CCC\n"})
        assert second.status_code == 429, second.text
    finally:
        celery_app.conf.task_always_eager = True
        if first_job_id:
            redis_client.delete(redis_store.job_meta_key(first_job_id))


def test_submitting_and_finishing_a_job_over_http_frees_the_slot_without_polling(
    redis_client, monkeypatch
):
    """The gap that made the leak invisible: test_releasing_a_job_frees_the_
    slot called release_job directly, and nothing asserted any endpoint
    ever calls it. This goes over real HTTP, lets a job actually finish via
    the fast in-process path, and checks the slot is free -- without ever
    touching GET /api/jobs/{id} (the thing that used to be the only release
    point along with DELETE).
    """
    from app.celery_app import celery_app
    from app.main import app

    monkeypatch.setattr(
        get_settings(), "RATE_LIMIT_MAX_CONCURRENT_JOBS", 1, raising=False
    )
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    try:
        client = TestClient(app)
        response = client.post("/api/jobs", json={"text": "CCO\n"})
        assert response.status_code == 200, response.text
        # fastapi.testclient.TestClient always reports this as the peer.
        assert redis_client.scard("orthonym:ip:testclient:jobs") == 0, (
            "a job that already finished (eager mode) still occupies its "
            "concurrent-job slot"
        )
        # And the cap of 1 is still enforceable for a second submission.
        response2 = client.post("/api/jobs", json={"text": "CCC\n"})
        assert response2.status_code == 200, response2.text
    finally:
        celery_app.conf.task_always_eager = False


def test_parse_preview_over_http_enforces_the_fast_cap(redis_client, monkeypatch):
    # Round 1 review, Important: /api/parse-preview was uncapped entirely.
    from app.main import app

    monkeypatch.setattr(
        get_settings(), "RATE_LIMIT_FAST_PER_MINUTE", 1, raising=False
    )
    c = TestClient(app)
    assert c.post("/api/parse-preview", json={"text": "CCO\n"}).status_code == 200
    assert c.post("/api/parse-preview", json={"text": "CCO\n"}).status_code == 429


def test_depict_over_http_enforces_its_own_cap(redis_client, monkeypatch):
    # Round 1 review, Important: /api/depict was uncapped entirely. Its own
    # (much larger) budget, not check_fast_allowed's -- see
    # check_depict_allowed's docstring for why.
    from app.main import app

    monkeypatch.setattr(
        get_settings(), "RATE_LIMIT_DEPICT_PER_MINUTE", 1, raising=False
    )
    c = TestClient(app)
    assert c.get("/api/depict", params={"smiles": "CCO"}).status_code == 200
    assert c.get("/api/depict", params={"smiles": "CCC"}).status_code == 429


def test_results_csv_over_http_enforces_the_fast_cap(redis_client, monkeypatch, job_id):
    # Round 1 review, Important: /api/jobs/{id}/results.csv was uncapped
    # entirely.
    from app.main import app

    monkeypatch.setattr(
        get_settings(), "RATE_LIMIT_FAST_PER_MINUTE", 1, raising=False
    )
    redis_store.create_job(job_id, total=1, fmt="smiles_list", client_ip="::1")
    redis_store.write_chunk(
        job_id, 0, [{"index": 0, "input": "CCO", "status": "pin"}]
    )
    redis_store.assemble_rows(job_id, n_chunks=1)
    redis_store.set_job_status(job_id, "done")

    c = TestClient(app)
    assert c.get(f"/api/jobs/{job_id}/results.csv").status_code == 200
    assert c.get(f"/api/jobs/{job_id}/results.csv").status_code == 429
