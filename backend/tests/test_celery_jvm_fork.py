"""The JVM fork contract.

Both JVM tests here fork from a FRESH subprocess parent rather than from the
pytest process. That is not fastidiousness: `tests/test_api.py` sorts first
and exercises `/api/explain-name`, which starts an in-process JVM through
OPSIN name decomposition. Every later fork in the same pytest process
therefore inherits a JVM, the child refuses it (by design), and a test that
forked from here would silently measure the *unhealthy* path while passing.

What the fork test must prove is that a healthy child starts and owns its
OWN JVM. Asserting only on the resulting tier is not enough, because a child
that refused an inherited JVM still returns the correct tier via the `java
-jar` subprocess fallback -- verified by probe. So the child reports
`opsin_available()` and whether `jvm_bridge._STARTED_PID` is its own pid, and
those are the load-bearing assertions.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent

# The fused-polycyclic Home example (ellipticine). With a live OPSIN round
# trip the engine ships a verified systematic name (tier systematic_verified,
# status "fallback"); without a round trip the status can only be best_effort,
# so "fallback" proves the child's JVM really ran the gate.
FUSED_POLYCYCLIC = "CC1=C2C=CN=CC2=C(C3=C1NC4=CC=CC=C43)C"

# os._exit(0) at the end of both probes is deliberate: a started JVM refuses
# to let the interpreter exit, which would turn a clean assertion failure
# into a subprocess timeout with no output to diagnose.

_IMPORT_PROBE = (
    "import sys, os; "
    "import app.orthonym_service; "
    "import jpype; "
    "sys.stdout.write('JVM_STARTED=%s' % jpype.isJVMStarted()); "
    "sys.stdout.flush(); "
    "os._exit(0)"
)

_FORK_PROBE = r'''
import json, multiprocessing as mp, os, sys

FUSED_POLYCYCLIC = "CC1=C2C=CN=CC2=C(C3=C1NC4=CC=CC=C43)C"


def _child(queue):
    from orthonym import jvm_bridge

    from app.orthonym_service import translate_one

    result = translate_one(FUSED_POLYCYCLIC, best_effort=True)
    queue.put({
        "pid": os.getpid(),
        "status": result.status,
        "roundtrip_smiles": result.roundtrip_smiles,
        "roundtrip_match": result.roundtrip_match,
        # opsin_available() re-decides per pid. True here means THIS process
        # can use the in-process JVM; False means it fell back to subprocess.
        "opsin_available": jvm_bridge.opsin_available(),
        # The pid that actually called startJVM. Equal to ours only if this
        # child started its own -- the whole point of the contract.
        "started_pid": jvm_bridge._STARTED_PID,
    })


if __name__ == "__main__":
    import jpype

    import app.orthonym_service  # the parent imports, exactly as Celery does

    parent_jvm_before_fork = jpype.isJVMStarted()

    ctx = mp.get_context("fork")
    queue = ctx.Queue()
    child = ctx.Process(target=_child, args=(queue,))
    child.start()
    payload = queue.get(timeout=600)
    child.join(timeout=120)

    payload["parent_pid"] = os.getpid()
    payload["parent_jvm_before_fork"] = parent_jvm_before_fork
    payload["child_exitcode"] = child.exitcode

    sys.stdout.write("FORK_PROBE=" + json.dumps(payload))
    sys.stdout.flush()
    os._exit(0)
'''


def _run_probe(source: str, timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", source],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(BACKEND_ROOT),
        env={**os.environ, "PYTHONPATH": str(BACKEND_ROOT)},
    )


def test_parent_import_does_not_start_a_jvm():
    """Importing the service must not start a JVM. Probed in a FRESH process.

    The property is about a fresh Celery parent: it imports
    app.orthonym_service, builds both namers, and must still own no JVM --
    because jvm_bridge refuses a JVM started by another pid, so every forked
    child would degrade to subprocess OPSIN and lose /explain entirely.
    """
    result = _run_probe(_IMPORT_PROBE, timeout=300)
    assert "JVM_STARTED=False" in result.stdout, (
        "Importing app.orthonym_service started a JVM in a fresh process. "
        "Children forked from such a parent refuse that JVM, fall back to a "
        "~216 ms subprocess per OPSIN call, and lose /explain and /teach.\n"
        f"stdout: {result.stdout!r}\nstderr: {result.stderr[-2000:]!r}"
    )


def test_forked_child_starts_and_owns_its_own_jvm():
    """The healthy path: fork from a JVM-free parent, child owns its own JVM.

    Every assertion below is load-bearing. In particular `opsin_available`
    and `started_pid` are what distinguish a healthy child from one that
    inherited, refused, and degraded to the subprocess path -- the degraded
    child still returns the correct tier, so tier assertions alone cannot
    tell the two apart.
    """
    result = _run_probe(_FORK_PROBE, timeout=900)
    marker = "FORK_PROBE="
    assert marker in result.stdout, (
        f"fork probe produced no result.\nstdout: {result.stdout!r}\n"
        f"stderr: {result.stderr[-3000:]!r}"
    )
    payload = json.loads(result.stdout.split(marker, 1)[1])

    # The parent must be JVM-free, or this test measures the unhealthy path.
    assert payload["parent_jvm_before_fork"] is False, payload
    # Really forked: under "spawn" the child re-imports and the inherited-JVM
    # hazard is never exercised at all.
    assert payload["pid"] != payload["parent_pid"], payload
    assert payload["child_exitcode"] == 0, payload

    # THE contract: this child started its own JVM and can use it.
    assert payload["opsin_available"] is True, payload
    assert payload["started_pid"] == payload["pid"], payload

    # And the tier is right. Anything but "fallback" here means the round
    # trip did not run, i.e. OPSIN was unreachable by any route.
    assert payload["status"] == "fallback", payload
    assert payload["roundtrip_smiles"] is not None, payload
    # "fallback" (systematic_verified) is RT-VERIFIED. True is correct here.
    assert payload["roundtrip_match"] is True, payload


def test_celery_app_pins_prefork_and_two_queues():
    from app.celery_app import celery_app

    queue_names = {q.name for q in celery_app.conf.task_queues}
    assert queue_names == {"fast", "batch"}
    # The whole JVM contract rests on fork semantics. Under -P threads or
    # gevent, worker_process_init never fires, so no child ever starts a JVM
    # or records a health status; under -P solo it fires in the parent.
    assert celery_app.conf.worker_pool == "prefork"
    # prefetch 1 is what makes progress reporting honest, and acks-late is
    # what requeues a chunk when a worker dies mid-molecule.
    assert celery_app.conf.worker_prefetch_multiplier == 1
    assert celery_app.conf.task_acks_late is True
    assert celery_app.conf.task_reject_on_worker_lost is True
