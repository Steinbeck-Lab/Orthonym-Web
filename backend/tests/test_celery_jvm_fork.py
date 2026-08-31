"""The JVM fork contract, tested with the same primitive Celery's prefork
pool uses.

Why this test exists: OpenSTOUT's SELF-01 self-consistency gate fails
*open*. Without a live JVM it cannot round-trip a candidate name through
OPSIN, so a name that should have downgraded to "fallback" ships as a
verified "pin". jvm_bridge.py defends against a JVM inherited across fork()
by recording the pid that called startJVM and refusing any other pid --
which means a parent that starts a JVM before forking silently disables
OPSIN in every child.

So: fork, name the molecule README.md nominates for exactly this check, and
assert the tier is real.
"""

import multiprocessing as mp
import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parent.parent

# Probing in a subprocess, not in-process: see the docstring of
# test_parent_import_does_not_start_a_jvm. os._exit(0) skips interpreter
# shutdown, because a started JVM refuses to let the process exit and would
# turn a clean assertion failure into a timeout.
_JVM_PROBE = (
    "import sys, os; "
    "import app.openstout_service; "
    "import jpype; "
    "sys.stdout.write('JVM_STARTED=%s' % jpype.isJVMStarted()); "
    "sys.stdout.flush(); "
    "os._exit(0)"
)

# The regression molecule from README.md. A fused polycyclic: OpenSTOUT can
# name it, but the name does not round-trip, so a working SELF-01 gate must
# report "fallback". A "pin" here means the gate silently failed open.
FUSED_POLYCYCLIC = "C1CC2CCC1(CC2)C3CCC4(CCC5(CCCC5C4C3)C)C"


def _name_in_child(queue) -> None:
    import os

    from app.openstout_service import translate_one

    result = translate_one(FUSED_POLYCYCLIC, best_effort=True)
    queue.put(
        {
            "pid": os.getpid(),
            "status": result.status,
            "roundtrip_smiles": result.roundtrip_smiles,
            "roundtrip_match": result.roundtrip_match,
        }
    )


def test_parent_import_does_not_start_a_jvm():
    """Importing the service must not start a JVM. Probed in a FRESH process.

    Asserting on *this* process would assert on test order, not on the
    property. pytest shares one process across the whole suite, and an
    earlier module (test_api.py, which sorts first) exercises
    /api/explain-name -- that starts a JVM through OPSIN name decomposition,
    a different codepath from translate_one/SELF-01. By the time this file
    runs, a JVM is already live for reasons that have nothing to do with the
    import under test.

    The property that actually matters is about a fresh Celery parent: it
    imports app.openstout_service, builds both namers, and must still own no
    JVM, because jvm_bridge refuses a JVM started by another pid and every
    forked child would therefore lose OPSIN and fail SELF-01 open.
    """
    result = subprocess.run(
        [sys.executable, "-c", _JVM_PROBE],
        capture_output=True,
        text=True,
        timeout=300,
        cwd=str(BACKEND_ROOT),
        env={**os.environ, "PYTHONPATH": str(BACKEND_ROOT)},
    )
    assert "JVM_STARTED=False" in result.stdout, (
        "Importing app.openstout_service started a JVM in a fresh process. "
        "Every Celery child forked from such a parent would refuse that JVM "
        "and lose OPSIN, so SELF-01 would fail open and a fallback could "
        f"ship labelled as a verified PIN.\n"
        f"stdout: {result.stdout!r}\nstderr: {result.stderr[-2000:]!r}"
    )


def test_forked_child_starts_its_own_jvm_and_the_tier_is_real():
    import os

    import app.openstout_service  # noqa: F401  -- parent imports, as Celery does

    ctx = mp.get_context("fork")
    queue = ctx.Queue()
    child = ctx.Process(target=_name_in_child, args=(queue,))
    child.start()
    payload = queue.get(timeout=300)
    child.join(timeout=60)

    # Prove we actually forked. Under "spawn" the child re-imports from
    # scratch and this test would no longer exercise the inherited-JVM
    # hazard at all -- it would pass while testing nothing.
    assert payload["pid"] != os.getpid()

    assert payload["status"] == "fallback", (
        f"Expected 'fallback' for the fused polycyclic, got "
        f"{payload['status']!r}. 'pin' means SELF-01 failed open in the "
        f"forked child -- the JVM did not start there."
    )

    # The JVM really lived in the child. A child that inherited and then
    # refused the parent's JVM gets None from opsin_parse, so both of these
    # would be None rather than a real SMILES and True. Tier T3
    # ("fallback") is defined in openstout_service.py as RT-VERIFIED via the
    # general engine, so True is the correct value here -- it is T4
    # ("best_effort") that is the OPSIN-unverified tier.
    assert payload["roundtrip_smiles"] is not None
    assert payload["roundtrip_match"] is True


def test_celery_app_uses_the_prefork_pool_and_two_queues():
    from app.celery_app import celery_app

    queue_names = {q.name for q in celery_app.conf.task_queues}
    assert queue_names == {"fast", "batch"}
    # prefetch 1 is what makes progress reporting honest, and acks-late is
    # what requeues a chunk when a worker dies mid-molecule.
    assert celery_app.conf.worker_prefetch_multiplier == 1
    assert celery_app.conf.task_acks_late is True
    assert celery_app.conf.task_reject_on_worker_lost is True
