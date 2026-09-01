"""C1: nothing refreshed the worker OPSIN status after boot, so a healthy
deployment 503'd ~120s after `docker compose up` and never recovered.

record_worker_opsin_status used to be written exactly once per worker
child, at worker_process_init -- no beat schedule, no task_prerun, no
worker_heartbeat. celery_app._start_status_heartbeat is the fix: a daemon
thread, started at the end of _start_child_jvm, that re-stamps the boot
verdict every `_WORKER_STATUS_TTL // 3` seconds for as long as the process
lives. These tests drive that thread directly rather than sleeping the
real 120s TTL: _WORKER_STATUS_TTL is monkeypatched down to a few seconds,
which also shortens the heartbeat's own interval (it is derived from
_WORKER_STATUS_TTL at thread-start time), so the same mechanism is
exercised on a test-sized clock.
"""

import threading
import time

from fastapi.testclient import TestClient

from app import redis_store
from app.celery_app import _start_status_heartbeat
from app.main import app

client = TestClient(app)


def test_heartbeat_keeps_a_healthy_deployment_healthy_past_the_ttl(
    no_worker_opsin, monkeypatch
):
    """The single most important untested behaviour named in the final
    review report: record a worker status, let more than
    _WORKER_STATUS_TTL pass, and confirm a naming endpoint still answers
    200 instead of 503.
    """
    monkeypatch.setattr(redis_store, "_WORKER_STATUS_TTL", 3)
    pid = 999900
    redis_store.record_worker_opsin_status(pid, ok=True)

    stop = threading.Event()
    thread = _start_status_heartbeat(pid, ok=True, stop_event=stop)
    assert thread.daemon is True, "a non-daemon heartbeat could block worker shutdown"
    try:
        # Longer than the shortened TTL (3s). Measured in the review
        # against the real 120s TTL: any_worker_has_opsin() was True at
        # 119s and False at 121s with nothing re-stamping it -- this is
        # the same gap, scaled down.
        time.sleep(3.5)

        assert redis_store.any_worker_has_opsin() is True, (
            "the worker status aged out even though the heartbeat should "
            "have re-stamped it well within the TTL -- a healthy "
            "deployment would 503 here"
        )

        response = client.post("/api/translate", json={"smiles": ["CCO"]})
        assert response.status_code == 200, response.text
        assert response.json()["results"][0]["status"] == "pin"
    finally:
        stop.set()
        thread.join(timeout=2)
        redis_store.get_redis().hdel("stitch:workers:opsin", str(pid))


def test_heartbeat_survives_a_write_failure_and_keeps_beating(monkeypatch):
    """Never raise into the worker: a transient Redis blip must cost one
    missed beat, not the whole heartbeat. An uncaught exception in a
    thread target ends that thread silently (Python's default
    threading.excepthook logs it and moves on) -- this child would then
    never beat again, which is exactly the C1 failure mode with extra
    steps.
    """
    calls = {"n": 0}

    def _boom(pid, ok):
        calls["n"] += 1
        raise RuntimeError("simulated redis blip")

    monkeypatch.setattr(redis_store, "record_worker_opsin_status", _boom)
    monkeypatch.setattr(redis_store, "_WORKER_STATUS_TTL", 3)

    stop = threading.Event()
    thread = _start_status_heartbeat(999901, ok=True, stop_event=stop)
    try:
        time.sleep(2.5)
        assert thread.is_alive(), "the heartbeat thread died on a write failure"
        assert calls["n"] >= 1, "the heartbeat never actually beat"
    finally:
        stop.set()
        thread.join(timeout=2)
