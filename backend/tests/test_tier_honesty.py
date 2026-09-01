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
