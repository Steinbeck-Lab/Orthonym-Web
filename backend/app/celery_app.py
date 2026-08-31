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
    logger.info("Celery parent: no JVM, safe to fork (pid %s)", os.getpid())


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
        record_worker_opsin_status(pid, ok=False)
        return

    decompose_ok = opsin_decompose.self_check()
    record_worker_opsin_status(pid, ok=decompose_ok)
    logger.info(
        "Celery child %s: OPSIN name decomposition %s",
        pid,
        "available" if decompose_ok else "DISABLED (see preceding log)",
    )
