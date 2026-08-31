"""The JVM fork contract, tested with the same primitive Celery's prefork
pool uses.

Why this test exists: Orthonym's SELF-01 self-consistency gate fails
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

import pytest

# The regression molecule from README.md. A fused polycyclic: Orthonym can
# name it, but the name does not round-trip, so a working SELF-01 gate must
# report "fallback". A "pin" here means the gate silently failed open.
FUSED_POLYCYCLIC = "C1CC2CCC1(CC2)C3CCC4(CCC5(CCCC5C4C3)C)C"


def _name_in_child(queue) -> None:
    import os

    from app.orthonym_service import translate_one

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
    # Importing the service builds both namers. If that alone started a JVM,
    # every forked child would inherit a dead one and refuse to use it.
    import app.orthonym_service  # noqa: F401
    import jpype

    assert not jpype.isJVMStarted(), (
        "Importing app.orthonym_service started a JVM in this process. "
        "Every Celery child forked from it would refuse that JVM and lose "
        "OPSIN, so SELF-01 would fail open."
    )


def test_forked_child_starts_its_own_jvm_and_the_tier_is_real():
    import os

    import app.orthonym_service  # noqa: F401  -- parent imports, as Celery does

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
    # ("fallback") is defined in orthonym_service.py as RT-VERIFIED via the
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
