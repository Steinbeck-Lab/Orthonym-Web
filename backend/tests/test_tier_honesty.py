"""The confidence ladder must never label a name better than it was proved.

STITCH's whole product claim is that a name's tier is honest: verified PIN ->
verified fallback -> best-effort (a real name, OPSIN-unverified) -> honest
abstain. PRODUCT.md principle 3 forbids conflating them anywhere.

Two separate guards live in openstout_service.translate_one and neither had a
test:

  * `best_effort=False` must mean no OPSIN-unverified name can EVER be
    produced -- the escalated namer is not consulted at all.
  * A tier that claims verification must not ship when the verification did
    not happen. _roundtrip_check returns (None, None) when OPSIN is
    unreachable, and SELF-01 fails OPEN, so an unverified candidate arrives
    labelled "pin".
"""

import pytest

from app import openstout_service


# --- best_effort=False: no unverified name may be produced -----------------


def test_best_effort_false_never_consults_the_escalated_namer(monkeypatch):
    """The gate is ONE branch -- `if status == "abstain" and best_effort:`.
    Delete or invert that `and best_effort` and the promise written down
    twice (schemas.py, this module's own docstring) silently dies, with the
    whole suite still green.

    Asserts the escalated namer is never CALLED, not merely that the result
    looks acceptable: a molecule the primary pass names successfully never
    reaches the escalation either way, so a result-shaped assertion could
    pass without the gate existing at all.
    """
    called: list[str] = []

    class _RecordingNamer:
        def name_tiered(self, smiles):
            called.append(smiles)
            return {"tier": "best_effort", "name": "ethanol", "formula": None, "limit_code": None}

    monkeypatch.setattr(
        openstout_service._namer,
        "name_tiered",
        lambda smiles: {"tier": "abstain", "name": None, "formula": "C2H6O", "limit_code": None},
    )
    monkeypatch.setattr(openstout_service, "_escalated_namer", _RecordingNamer())

    item = openstout_service.translate_one("CCO", best_effort=False)

    assert called == [], (
        "the escalated namer ran with best_effort=False; an OPSIN-unverified "
        "name can now be produced by a caller who explicitly refused them"
    )
    assert item.status == "abstain"
    assert item.name is None


def test_best_effort_true_still_escalates(monkeypatch):
    """The good-case half of the fail-closed pair. A guard that refuses the
    bad case by refusing EVERYTHING is not a guard, it is an outage -- and
    that exact shape (a fail-closed check that also blocked the healthy
    path) took this site down for the whole of its 120s TTL once already.
    """
    called: list[str] = []

    class _RecordingNamer:
        def name_tiered(self, smiles):
            called.append(smiles)
            return {"tier": "best_effort", "name": "ethanol", "formula": None, "limit_code": None}

    monkeypatch.setattr(
        openstout_service._namer,
        "name_tiered",
        lambda smiles: {"tier": "abstain", "name": None, "formula": "C2H6O", "limit_code": None},
    )
    monkeypatch.setattr(openstout_service, "_escalated_namer", _RecordingNamer())

    item = openstout_service.translate_one("CCO", best_effort=True)

    assert called == ["CCO"], "the escalation never ran; best_effort=True is a no-op"
    assert item.status == "best_effort"
    assert item.name == "ethanol"


# --- a verified tier must not ship without its proof -----------------------


def test_a_pin_is_downgraded_when_opsin_could_not_verify_it(monkeypatch):
    """C3-followup, the backend half.

    SELF-01 uses the same opsin_parse() as the visible round-trip check, so a
    null roundtrip_smiles on a "pin" row can only mean OPSIN was unreachable:
    SELF-01 failed OPEN and shipped an unverified candidate wearing a
    verified label. The cache already refuses to persist that row for 7 days
    (name_cache.put_cached), but it was still SERVED once, and the frontend
    renders "pin" with the double rule that means round-trip confirmed.

    Declining to cache a lie is not the same as declining to tell it.
    """
    monkeypatch.setattr(openstout_service, "opsin_parse", lambda name: None)

    item = openstout_service.translate_one("CCO", best_effort=True)

    assert item.roundtrip_smiles is None
    assert item.status == "best_effort", (
        f"served status={item.status!r} with no round-trip proof; that is a "
        "verified tier claiming a verification that never happened"
    )
    assert item.name is not None, "the name itself is real and must survive the downgrade"


def test_an_unverifiable_name_abstains_when_the_caller_refused_unverified_ones(
    monkeypatch,
):
    """The interaction between the two guards, which is the part that is easy
    to get wrong: downgrading an unprovable "pin" to "best_effort" would hand
    an OPSIN-unverified name to a caller who passed best_effort=False
    precisely to refuse them. For that caller the honest answer is abstain.
    """
    monkeypatch.setattr(openstout_service, "opsin_parse", lambda name: None)

    item = openstout_service.translate_one("CCO", best_effort=False)

    assert item.status == "abstain", (
        f"served status={item.status!r} to a caller who refused OPSIN-"
        "unverified names"
    )
    assert item.name is None


def test_a_genuinely_verified_pin_is_untouched():
    """Vacuity guard: with OPSIN really available, a real pin stays a pin.
    Without this, downgrading everything unconditionally would pass every
    assertion above.
    """
    item = openstout_service.translate_one("CCO", best_effort=True)

    assert item.status == "pin"
    assert item.roundtrip_smiles is not None
    assert item.roundtrip_match is True


def test_a_best_effort_name_is_not_downgraded_for_lacking_proof(monkeypatch):
    """best_effort is ALREADY the honest label for "a real name, OPSIN-
    unverified" -- it claims no verification, so a null round-trip is not a
    contradiction and must not push it to abstain. Only tiers that CLAIM
    verification (pin, fallback) are downgraded.
    """
    monkeypatch.setattr(openstout_service, "opsin_parse", lambda name: None)
    monkeypatch.setattr(
        openstout_service._namer,
        "name_tiered",
        lambda smiles: {"tier": "best_effort", "name": "ethanol", "formula": None, "limit_code": None},
    )

    item = openstout_service.translate_one("CCO", best_effort=True)

    assert item.status == "best_effort"
    assert item.name == "ethanol"


# --- naming health vs /explain health are different questions --------------


def test_a_broken_reflection_shim_does_not_take_naming_offline(monkeypatch):
    """CC5: the worker stamped its health from opsin_decompose.self_check(),
    which is the /explain REFLECTION-SHAPE probe, not the naming one.

    _get_handles() returns None for two unrelated reasons: OPSIN itself is
    unavailable (naming genuinely cannot be verified -- refuse), or OPSIN is
    fine but its package-private parse-tree shape changed (only /explain and
    /teach break -- naming is unaffected). Conflating them means a vendored
    OPSIN bump that moves an internal class takes /api/translate,
    /api/jobs and the three GET endpoints down site-wide with a 503 that says
    "OPSIN cannot verify any name" -- which would be false.

    That is spec section 5's Failure A being treated as Failure B, the exact
    conflation the spec's own correction exists to prevent.
    """
    from app import celery_app as celery_mod

    monkeypatch.setattr(celery_mod, "_jvm_is_started", lambda: False)
    # OPSIN itself is healthy; only the reflection shim is broken.
    monkeypatch.setattr(celery_mod, "_opsin_can_verify", lambda: True)
    # celery_app imports opsin_decompose inside the function (it must not
    # start a JVM in the pre-fork parent), so patch the source module.
    from app import opsin_decompose

    monkeypatch.setattr(opsin_decompose, "self_check", lambda: False)

    stamped: dict = {}
    from app import redis_store

    monkeypatch.setattr(
        redis_store, "record_worker_opsin_status", lambda pid, ok: stamped.update(ok=ok)
    )
    monkeypatch.setattr(
        celery_mod, "_start_status_heartbeat", lambda pid, ok, stop_event=None: None
    )

    celery_mod._start_child_jvm()

    assert stamped.get("ok") is True, (
        "a broken /explain reflection shim marked this worker as having no "
        "usable OPSIN, so every naming endpoint 503s site-wide even though "
        "name verification works perfectly"
    )


def test_opsin_being_genuinely_unavailable_still_refuses(monkeypatch):
    """The fail-closed half. Splitting the two signals must not turn the
    naming gate into a rubber stamp: when OPSIN really cannot verify a name,
    this worker must still report unhealthy so require_a_live_jvm() refuses
    rather than shipping a fallback labelled pin.
    """
    from app import celery_app as celery_mod

    monkeypatch.setattr(celery_mod, "_jvm_is_started", lambda: False)
    monkeypatch.setattr(celery_mod, "_opsin_can_verify", lambda: False)
    from app import opsin_decompose

    monkeypatch.setattr(opsin_decompose, "self_check", lambda: True)

    stamped: dict = {}
    from app import redis_store

    monkeypatch.setattr(
        redis_store, "record_worker_opsin_status", lambda pid, ok: stamped.update(ok=ok)
    )
    monkeypatch.setattr(
        celery_mod, "_start_status_heartbeat", lambda pid, ok, stop_event=None: None
    )

    celery_mod._start_child_jvm()

    assert stamped.get("ok") is False, (
        "OPSIN cannot verify names but this worker reported healthy; "
        "require_a_live_jvm() would admit work nobody can verify"
    )
