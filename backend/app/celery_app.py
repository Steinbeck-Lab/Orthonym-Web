"""Celery application, queues, and the JVM guards.

Two queues with a dedicated worker each, rather than one queue with a
priority field: a dedicated worker per queue is the only arrangement where a
long batch physically cannot occupy the last slot an interactive request
needs. This mirrors ChemAudit's default/high_priority split.

The prefork pool is deliberate and pinned. jvm_bridge.py's contract says
Orthonym is built for a process pool where "laziness means the parent starts
no JVM and each worker starts its own" -- prefork is exactly that. Under
-P threads or gevent, worker_process_init never fires, so no child would
start a JVM or record a health status.

What a lost JVM actually costs (see spec section 5, which an earlier version
of this docstring got wrong): a child that refuses a JVM inherited across
fork() still returns CORRECT tiers, because opsin_parse falls through to a
`java -jar` subprocess. It loses throughput -- 0.8 ms per OPSIN call becomes
~216 ms, several calls per molecule -- and it loses /explain and /teach
entirely, because opsin_decompose hard-gates on opsin_available() with no
subprocess fallback. The mislabeled-tier fail-open is a different failure:
OPSIN unavailable altogether, which Task 8's build-time check guards.
"""

import logging
import os
import threading

from celery import Celery
from celery.signals import celeryd_init, worker_process_init
from kombu import Exchange, Queue

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

celery_app = Celery(
    "orthonym",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks"],
)

_exchange = Exchange("orthonym", type="direct")

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    result_expires=settings.JOB_RESULT_TTL_SECONDS,
    task_track_started=True,
    # Pinned, not defaulted: the entire JVM contract rests on fork.
    worker_pool="prefork",
    # One task at a time per child, so the molecule counter in Redis
    # reflects work actually finished rather than work merely reserved.
    worker_prefetch_multiplier=1,
    # Acknowledge after completion and requeue on worker loss: a chunk
    # killed by the hard time limit comes back rather than vanishing.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_soft_time_limit=settings.CHUNK_SOFT_TIME_LIMIT,
    task_time_limit=settings.CHUNK_HARD_TIME_LIMIT,
    task_queues=(
        Queue("fast", _exchange, routing_key="fast"),
        Queue("batch", _exchange, routing_key="batch"),
    ),
    task_default_queue="batch",
    task_default_exchange="orthonym",
    task_default_routing_key="batch",
    task_routes={
        "app.tasks.translate_job_inline": {"queue": "fast"},
        "app.tasks.run_chunk": {"queue": "batch"},
        "app.tasks.finalize_job": {"queue": "batch"},
        "app.tasks.mark_job_failed": {"queue": "batch"},
        "app.tasks.translate_fast": {"queue": "fast"},
        "app.tasks.explain_smiles": {"queue": "fast"},
        "app.tasks.explain_iupac_name": {"queue": "fast"},
        "app.tasks.name_to_smiles": {"queue": "fast"},
    },
)


def _jvm_is_started() -> bool:
    """Indirection so the guards are testable without starting a real JVM."""
    import jpype

    return bool(jpype.isJVMStarted())


@celeryd_init.connect
def _assert_parent_has_no_jvm(**_kwargs) -> None:
    """Runs in the worker PARENT, after conf.include imports, before any fork.

    jvm_bridge records the pid that called startJVM and refuses a JVM started
    by any other pid. A JVM here therefore means every child degrades to a
    ~216 ms subprocess per OPSIN call and loses /explain entirely.

    SystemExit, not a plain exception: Celery's Signal.send wraps receivers in
    `except Exception`, logs, and returns the exception as a response that
    celery/apps/worker.py discards -- a RuntimeError would be swallowed and
    the worker would boot anyway. SystemExit is a BaseException and escapes.
    """
    if _jvm_is_started():
        raise SystemExit(
            "A JVM was already started in the Celery parent process "
            f"(pid {os.getpid()}). Forked children refuse a JVM started by "
            "another pid (see jvm_bridge.py's fork-safe contract), so every "
            "child would fall back to a ~216 ms subprocess per OPSIN call "
            "and lose /explain and /teach entirely. Refusing to start. Find "
            "the import that calls into OPSIN at module scope -- most likely "
            "something app.tasks pulls in -- and make it lazy."
        )
    # print, not logger.info: celeryd_init fires BEFORE Celery calls
    # setup_logging(), so a logger call here is silently dropped and never
    # reaches `docker compose logs`. Task 8 found this by looking for the
    # line and not finding it -- the guard was working, but its
    # confirmation was unobservable, which for a boot-time safety check is
    # most of its value. The failure path is already visible because
    # SystemExit's message goes to stderr; this makes the success path
    # visible too.
    print(
        f"Celery parent: no JVM, safe to fork (pid {os.getpid()})",
        flush=True,
    )


def _start_status_heartbeat(
    pid: int, ok: bool, stop_event: threading.Event | None = None
) -> threading.Thread:
    """Start a daemon thread that re-stamps this child's boot verdict every
    `_WORKER_STATUS_TTL // 3` seconds, for as long as the process lives.

    Final review report, C1: record_worker_opsin_status used to be called
    exactly once per child, at worker_process_init, and nothing else ever
    called it again -- no beat schedule, no task_prerun, no
    worker_heartbeat. redis_store._WORKER_STATUS_TTL's own docstring rests
    on "as long as at least one worker writes periodically"; nothing did,
    so any_worker_has_opsin() went False ~120s after every worker's last
    boot and stayed False forever, 503ing every naming endpoint on an
    otherwise perfectly healthy deployment.

    Re-stamping on the task path (task_prerun) was considered and
    rejected: it deadlocks on an idle site. No traffic means no stamps,
    the status ages out, require_a_live_jvm() 503s -- and a 503'd request
    never reaches a worker, so nothing re-stamps. The gate would block the
    very traffic that would refresh it. A timer that runs regardless of
    traffic is the only thing that closes that loop, and there is no
    recurring per-child Celery signal to hang one on in prefork mode, so
    it has to be this thread.

    This re-stamps the BOOT verdict, not a fresh self_check() -- calling
    self_check() again would just return opsin_decompose._get_handles()'s
    cached answer anyway. So this thread proves "this child process is
    still alive," not "OPSIN still works in this child" -- a JVM that dies
    mid-life keeps reporting healthy. That is the same exposure the code
    already had (the stamp was always a boot verdict); it is not widened
    by this fix, but it is why C3's cache guard is independently required
    and not made redundant by this thread.

    A child wedged inside a single naming call past _WORKER_STATUS_TTL
    (up to CHUNK_HARD_TIME_LIMIT = 900s) does NOT keep beating: RDKit's
    Boost.Python wrappers do not release the GIL (see jobs_api.py's
    MAX_DEPICT_SMILES comment), so this thread cannot be scheduled while
    that call holds it, misses its beats, and the child correctly drops
    out of any_worker_has_opsin(). That is transient and fail-closed --
    the wedged child stops being routed new work while its siblings, an
    ANY check, keep serving -- and self-corrects the moment the call
    returns and the next beat lands.

    daemon=True so it can never block worker shutdown. The write itself is
    wrapped in try/except: a transient Redis blip must cost one missed
    beat, not the heartbeat itself -- an uncaught exception here would end
    the thread silently (Python's default threading.excepthook logs and
    moves on) and this child would never beat again.

    `stop_event` is normally None (the thread simply runs until the
    process exits); tests pass their own Event so they can shut the thread
    down cleanly instead of leaking a background thread into the rest of
    the suite.
    """
    from app.redis_store import _WORKER_STATUS_TTL, record_worker_opsin_status

    # max(1, ...): if _WORKER_STATUS_TTL is ever lowered below 3, a bare
    # `// 3` is 0, which turns `event.wait(interval)` into a busy loop
    # hammering Redis on every iteration instead of a periodic heartbeat.
    interval = max(1, _WORKER_STATUS_TTL // 3)
    event = stop_event if stop_event is not None else threading.Event()

    def _beat() -> None:
        # event.wait(interval) sleeps for `interval` seconds UNLESS the
        # event is set first, in which case it returns True immediately
        # and the loop exits -- a sleep that a test can cut short.
        while not event.wait(interval):
            try:
                record_worker_opsin_status(pid, ok=ok)
            except Exception:
                logger.exception(
                    "Celery child %s: heartbeat failed to re-stamp its "
                    "OPSIN status; will retry in %ss.",
                    pid,
                    interval,
                )

    thread = threading.Thread(
        target=_beat, name=f"opsin-status-heartbeat-{pid}", daemon=True
    )
    thread.start()
    logger.info(
        "Celery child %s: started OPSIN status heartbeat (every %ss).",
        pid,
        interval,
    )
    return thread


def _stamp_without_raising(record, pid: int, *, ok: bool) -> None:
    """Write this child's boot verdict, swallowing a Redis failure.

    Final review report, C1-secondary. This one-shot stamp used to be a bare
    call, and _start_status_heartbeat ran only AFTER it. A Redis error here --
    a `docker compose up` where Redis is still warming is the realistic case
    -- therefore raised out of _start_child_jvm BEFORE the heartbeat existed.
    Celery 5.6.3 catches that inside Signal.send and discards it (see
    _assert_parent_has_no_jvm's note on the same mechanism), so the child
    boots looking healthy while never stamping and never beating: invisible
    to any_worker_has_opsin() for the life of the process. If every child
    lands in that window, /api/health reports DEGRADED and every naming
    endpoint 503s on a perfectly healthy deployment, with nothing to recover
    it.

    The heartbeat is exactly that recovery path -- it already tolerates a
    failed write and retries every _WORKER_STATUS_TTL // 3 seconds -- which
    is precisely why this call must never be able to skip it. Losing the
    boot stamp costs at most one heartbeat interval of invisibility;
    losing the heartbeat costs the child's whole life.

    Fail-closed either way: a child that cannot stamp is simply not counted
    as having a JVM, so nothing serves names nobody verified.
    """
    try:
        record(pid, ok=ok)
    except Exception:
        logger.exception(
            "Celery child %s: could not record its boot OPSIN status "
            "(ok=%s). The heartbeat below will retry; this child stays "
            "invisible to any_worker_has_opsin() until a beat lands.",
            pid,
            ok,
        )


@worker_process_init.connect
def _start_child_jvm(**_kwargs) -> None:
    """Runs inside each forked CHILD. This is where its own JVM starts.

    This is the only guard that does not depend on the parent's, so it checks
    the inherited case itself rather than trusting that celeryd_init caught
    it.

    Never raise from here. billiard invokes this initializer in after_fork(),
    outside its own try/except, so an escaping exception exits the child
    non-zero and the pool respawns it forever. os._exit is the only safe way
    to fail hard.
    """
    from app import opsin_decompose
    from app.redis_store import record_worker_opsin_status

    pid = os.getpid()

    if _jvm_is_started():
        # Inherited across fork. This child can never own it, so OPSIN will
        # work only via subprocess and opsin_decompose will not work at all.
        logger.critical(
            "Celery child %s inherited a JVM from its parent and cannot use "
            "it. OPSIN will fall back to a ~216 ms subprocess per call and "
            "/explain will be unavailable in this child. The parent started "
            "a JVM before forking -- see _assert_parent_has_no_jvm.",
            pid,
        )
        _stamp_without_raising(record_worker_opsin_status, pid, ok=False)
        try:
            _start_status_heartbeat(pid, ok=False)
        except Exception:
            # "Never raise from here" (see the module docstring above): a
            # thread that fails to start (e.g. threading.Thread.start()
            # raising RuntimeError under resource pressure) must not take
            # the child down with it. The safe direction: this child simply
            # ages out of any_worker_has_opsin() after _WORKER_STATUS_TTL
            # and stops being routed naming work, rather than serving
            # names with nobody re-verifying its JVM stayed alive.
            logger.exception(
                "Celery child %s: failed to start the OPSIN status "
                "heartbeat; this child will age out of any_worker_has_opsin() "
                "after _WORKER_STATUS_TTL and stop serving.",
                pid,
            )
        return

    decompose_ok = opsin_decompose.self_check()
    _stamp_without_raising(record_worker_opsin_status, pid, ok=decompose_ok)
    logger.info(
        "Celery child %s: OPSIN name decomposition %s",
        pid,
        "available" if decompose_ok else "DISABLED (see preceding log)",
    )
    try:
        _start_status_heartbeat(pid, ok=decompose_ok)
    except Exception:
        # Same "never raise from here" contract as the inherited-JVM branch
        # above: a failure to start the heartbeat thread must not escape
        # and take the child down with it. Fail-closed direction: this
        # child ages out of any_worker_has_opsin() after
        # _WORKER_STATUS_TTL and stops being routed naming work.
        logger.exception(
            "Celery child %s: failed to start the OPSIN status heartbeat; "
            "this child will age out of any_worker_has_opsin() after "
            "_WORKER_STATUS_TTL and stop serving.",
            pid,
        )
