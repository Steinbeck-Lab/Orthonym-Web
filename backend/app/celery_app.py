"""Celery application, queues, and the JVM fork guards.

Two queues with a dedicated worker each, rather than one queue with a
priority field: a dedicated worker per queue is the only arrangement where a
long batch physically cannot occupy the last slot an interactive request
needs. This mirrors ChemAudit's default/high_priority split.

The prefork pool is deliberate. jvm_bridge.py's contract says Orthonym is
built for a process pool where "laziness means the parent starts no JVM and
each worker starts its own" -- prefork is exactly that. The guards below
enforce the "parent starts no JVM" half, because if it is ever violated,
every child refuses the inherited JVM, SELF-01 fails open, and a fallback
ships labelled as a verified PIN.
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
    },
)


def _jvm_is_started() -> bool:
    """Indirection so the guard is testable without starting a real JVM."""
    import jpype

    return bool(jpype.isJVMStarted())


@celeryd_init.connect
def _assert_parent_has_no_jvm(**_kwargs) -> None:
    """Runs in the worker PARENT, before any fork.

    jvm_bridge records the pid that called startJVM and refuses a JVM
    started by any other pid. So a JVM here means every child silently
    loses OPSIN. Refusing to boot is the only safe response: a worker that
    starts anyway would serve names with a confidence tier nobody verified.
    """
    if _jvm_is_started():
        raise RuntimeError(
            "A JVM was already started in the Celery parent process "
            f"(pid {os.getpid()}). Forked children would refuse it "
            "(see jvm_bridge.py's fork-safe contract), Orthonym's SELF-01 "
            "gate would fail open, and a fallback name could ship labelled "
            "as a verified PIN. Refusing to start. Find the import that "
            "calls into OPSIN at module scope and make it lazy."
        )
    logger.info("Celery parent: no JVM, safe to fork (pid %s)", os.getpid())


@worker_process_init.connect
def _start_child_jvm(**_kwargs) -> None:
    """Runs inside each forked CHILD. This is where its own JVM starts.

    Doing it at boot rather than on the first task means a broken JVM is
    visible in the worker log immediately, and /api/health can report it
    before a user ever sees a mislabelled tier.
    """
    from app import opsin_decompose
    from app.redis_store import record_worker_opsin_status

    pid = os.getpid()
    decompose_ok = opsin_decompose.self_check()
    record_worker_opsin_status(pid, ok=decompose_ok)
    logger.info(
        "Celery child %s: OPSIN name decomposition %s",
        pid,
        "available" if decompose_ok else "DISABLED (see preceding log)",
    )
