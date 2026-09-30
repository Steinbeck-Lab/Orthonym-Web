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

import pytest

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
        # Margin must exceed the TTL by MORE than one second, not just
        # "longer than the TTL". Both the stamp and the read floor their
        # timestamp with int(time.time()), so the integer difference
        # between them is off by one depending purely on sub-second
        # alignment -- a margin of TTL + 1 (e.g. sleep(3.5) against a
        # TTL of 3) satisfies `<= TTL` about half the time and passes
        # anyway, which is exactly how this test shipped green while
        # guarding nothing (confirmed: neutering the heartbeat entirely
        # still passed 7/12 jittered runs at that margin). TTL + 2 removes
        # the truncation error instead of gambling on it. Do not tighten
        # this back to "just over the TTL".
        time.sleep(5)

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
        redis_store.get_redis().hdel("orthonym:workers:opsin", str(pid))


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


def test_a_redis_blip_at_boot_does_not_stop_the_heartbeat_from_starting(monkeypatch):
    """C1-secondary: the boot stamp must never be able to prevent the
    heartbeat that would heal it.

    _start_child_jvm called record_worker_opsin_status() UNGUARDED and only
    reached _start_status_heartbeat() afterwards. A Redis error at child boot
    -- a `docker compose up` where Redis is still warming is the realistic
    case -- therefore raised out of the initializer BEFORE the heartbeat
    existed. Celery 5.6.3 catches that raise inside Signal.send and discards
    it, so the child boots and looks fine, but it never stamps and never
    beats: it is invisible to any_worker_has_opsin() forever. If every child
    lands in that window, /api/health reports DEGRADED and every naming
    endpoint 503s on a perfectly healthy deployment, with no self-recovery.

    The heartbeat already tolerates a failed write and retries (see
    test_heartbeat_survives_a_write_failure_and_keeps_beating), so starting
    it is exactly the recovery path -- which is why the one-shot stamp must
    not be able to skip it.
    """
    import app.celery_app as celery_app

    calls: list[tuple[int, bool]] = []

    def _boom(pid, ok):
        calls.append((pid, ok))
        raise ConnectionError("Redis is still warming up")

    started: list[int] = []

    def _fake_heartbeat(pid, ok, stop_event=None):
        started.append(pid)
        return threading.Thread(target=lambda: None)

    monkeypatch.setattr(celery_app, "_jvm_is_started", lambda: False)
    monkeypatch.setattr(redis_store, "record_worker_opsin_status", _boom)
    monkeypatch.setattr(celery_app, "_start_status_heartbeat", _fake_heartbeat)

    # Must not raise: "never raise from here" is the initializer's contract.
    celery_app._start_child_jvm()

    assert calls, "the boot stamp was never attempted"
    assert started, (
        "the heartbeat never started, so this child can never re-stamp and is "
        "invisible to any_worker_has_opsin() for the life of the process"
    )


def test_a_redis_blip_at_boot_does_not_stop_the_heartbeat_in_the_inherited_jvm_branch(
    monkeypatch,
):
    """Same defect, the other branch. _start_child_jvm has two paths that
    stamp-then-start-a-heartbeat, and the inherited-JVM path returns early --
    so a fix applied only to the healthy path leaves this one broken, and no
    test that exercised only the healthy path would notice.
    """
    import app.celery_app as celery_app

    def _boom(pid, ok):
        raise ConnectionError("Redis is still warming up")

    started: list[int] = []

    def _fake_heartbeat(pid, ok, stop_event=None):
        started.append(pid)
        return threading.Thread(target=lambda: None)

    monkeypatch.setattr(celery_app, "_jvm_is_started", lambda: True)
    monkeypatch.setattr(redis_store, "record_worker_opsin_status", _boom)
    monkeypatch.setattr(celery_app, "_start_status_heartbeat", _fake_heartbeat)

    celery_app._start_child_jvm()

    assert started, (
        "the inherited-JVM branch skipped its heartbeat when the boot stamp "
        "raised; that child is invisible to any_worker_has_opsin() forever"
    )


def test_the_heartbeat_probes_opsin_rather_than_replaying_the_boot_verdict(monkeypatch):
    """C1-residual: the heartbeat re-stamped the value computed at boot, so a
    worker whose JVM died without the process dying kept advertising health.

    any_worker_has_opsin() stayed True, require_a_live_jvm() admitted the
    request, and a name that should have read "fallback" shipped labelled
    "pin". C3's cache guard stops that persisting for 7 days; it does not
    stop it being served once.

    A real probe costs 0.19 ms (measured, mean over 200 calls), so running one
    every _WORKER_STATUS_TTL // 3 seconds is free. opsin_available() cannot
    substitute: orthonym.jvm_bridge._ensure_jvm caches its answer per
    process, so it replays the boot decision exactly like the old code did.
    """
    import app.celery_app as celery_app

    monkeypatch.setattr(redis_store, "_WORKER_STATUS_TTL", 3)
    alive = {"ok": True}
    monkeypatch.setattr(celery_app, "_opsin_liveness_probe", lambda: alive["ok"])

    stamps: list[bool] = []
    monkeypatch.setattr(
        redis_store, "record_worker_opsin_status", lambda pid, ok: stamps.append(ok)
    )

    stop = threading.Event()
    celery_app._start_status_heartbeat(999901, ok=True, stop_event=stop)
    try:
        deadline = time.time() + 6
        while not stamps and time.time() < deadline:
            time.sleep(0.05)
        assert stamps, "the heartbeat never stamped at all"
        assert stamps[-1] is True, "a healthy worker stopped reporting healthy"

        alive["ok"] = False  # the JVM dies; the process does not
        before = len(stamps)
        deadline = time.time() + 6
        while len(stamps) == before and time.time() < deadline:
            time.sleep(0.05)
    finally:
        stop.set()

    assert len(stamps) > before, "the heartbeat stopped beating"
    assert stamps[-1] is False, (
        "the heartbeat is still replaying its boot verdict; a worker whose JVM "
        "died keeps advertising health and will serve an unverified name "
        "labelled as a verified one"
    )


def test_a_worker_stamped_unhealthy_at_boot_cannot_probe_its_way_to_healthy(
    monkeypatch,
):
    """The boot verdict is a ceiling on every beat. The inherited-JVM child is
    stamped False on purpose and can never own a JVM; if the heartbeat believed
    the probe alone it would flip that child to healthy on its first beat.
    """
    import app.celery_app as celery_app

    monkeypatch.setattr(redis_store, "_WORKER_STATUS_TTL", 3)
    monkeypatch.setattr(celery_app, "_opsin_liveness_probe", lambda: True)
    stamps: list[bool] = []
    monkeypatch.setattr(
        redis_store, "record_worker_opsin_status", lambda pid, ok: stamps.append(ok)
    )

    stop = threading.Event()
    celery_app._start_status_heartbeat(999902, ok=False, stop_event=stop)
    try:
        deadline = time.time() + 6
        while len(stamps) < 2 and time.time() < deadline:
            time.sleep(0.05)
    finally:
        stop.set()

    assert len(stamps) >= 2, "the heartbeat never beat"
    assert not any(stamps), "a child stamped unhealthy at boot was stamped healthy"


@pytest.mark.parametrize("naming_ok", [True, False])
def test_the_boot_stamp_and_heartbeat_carry_the_naming_verdict(monkeypatch, naming_ok):
    """What the child stamps at boot, and hands the heartbeat as its ceiling,
    is what OPSIN name verification said -- not a constant either way.
    """
    import app.celery_app as celery_app

    stamps: list[bool] = []
    ceilings: list[bool] = []

    def _fake_heartbeat(pid, ok, stop_event=None):
        ceilings.append(ok)
        return threading.Thread(target=lambda: None)

    monkeypatch.setattr(celery_app, "_jvm_is_started", lambda: False)
    monkeypatch.setattr(celery_app, "_opsin_can_verify", lambda: naming_ok)
    monkeypatch.setattr(
        redis_store, "record_worker_opsin_status", lambda pid, ok: stamps.append(ok)
    )
    monkeypatch.setattr(celery_app, "_start_status_heartbeat", _fake_heartbeat)

    celery_app._start_child_jvm()

    assert stamps == [naming_ok]
    assert ceilings == [naming_ok]


def test_a_child_that_inherited_a_jvm_is_stamped_unhealthy(monkeypatch):
    # It can never own that JVM, so it must not be counted as having a usable
    # OPSIN -- neither at boot nor as the ceiling for its heartbeat.
    import app.celery_app as celery_app

    stamps: list[bool] = []
    ceilings: list[bool] = []

    def _fake_heartbeat(pid, ok, stop_event=None):
        ceilings.append(ok)
        return threading.Thread(target=lambda: None)

    monkeypatch.setattr(celery_app, "_jvm_is_started", lambda: True)
    monkeypatch.setattr(
        redis_store, "record_worker_opsin_status", lambda pid, ok: stamps.append(ok)
    )
    monkeypatch.setattr(celery_app, "_start_status_heartbeat", _fake_heartbeat)

    celery_app._start_child_jvm()

    assert stamps == [False]
    assert ceilings == [False]


def test_the_liveness_probe_rejects_a_jvm_that_answers_wrongly(monkeypatch):
    """A JVM that responds but returns nonsense is dead for our purposes: the
    round-trip check it backs would compare against garbage. The probe must
    assert on the ANSWER, not merely on the absence of an exception.
    """
    import app.celery_app as celery_app
    from app import orthonym_service

    monkeypatch.setattr(orthonym_service, "opsin_parse", lambda name: "not-a-smiles!!")
    assert celery_app._opsin_liveness_probe() is False

    monkeypatch.setattr(orthonym_service, "opsin_parse", lambda name: None)
    assert celery_app._opsin_liveness_probe() is False

    # A well-formed but WRONG molecule: parsing it proves nothing about the
    # JVM being right, so the answer itself has to be compared.
    monkeypatch.setattr(orthonym_service, "opsin_parse", lambda name: "CC")
    assert celery_app._opsin_liveness_probe() is False

    def _boom(name):
        raise RuntimeError("JVM is gone")

    monkeypatch.setattr(orthonym_service, "opsin_parse", _boom)
    assert celery_app._opsin_liveness_probe() is False, "a raising probe must fail closed"


def test_the_liveness_probe_passes_against_a_real_jvm():
    """Vacuity guard: with OPSIN genuinely up the probe must return True, or
    the fix above is just a permanent outage that happens to pass its own
    negative tests.
    """
    import app.celery_app as celery_app

    assert celery_app._opsin_liveness_probe() is True
