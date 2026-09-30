"""The confidence ladder must never label a name better than it was proved.

Orthonym's whole product claim is that a name's tier is honest: verified PIN ->
verified fallback -> best-effort (a real name from the general engine) -> honest
abstain. PRODUCT.md principle 3 forbids conflating them anywhere.

Two separate guards live in orthonym_service.translate_one and neither had a
test:

  * `best_effort=False` must mean the escalated namer is not consulted at
    all. (The primary pass no longer gives a verified name tier best_effort;
    see the test at the end of this section.)
  * A status that claims verification must not ship when the verification
    did not happen. _roundtrip_check returns (None, None) when OPSIN is
    unreachable, and SELF-01 fails OPEN, so an unverified candidate arrives
    labelled "pin".
"""

import pytest

from app import orthonym_service
from app.main import EXAMPLES


# --- best_effort=False: no best-effort name may be produced ----------------


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
        orthonym_service._namer,
        "name_tiered",
        lambda smiles: {"tier": "abstain", "name": None, "formula": "C2H6O", "limit_code": None},
    )
    monkeypatch.setattr(orthonym_service, "_escalated_namer", _RecordingNamer())

    item = orthonym_service.translate_one("CCO", best_effort=False)

    assert called == [], (
        "the escalated namer ran with best_effort=False; a best-effort "
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
        orthonym_service._namer,
        "name_tiered",
        lambda smiles: {"tier": "abstain", "name": None, "formula": "C2H6O", "limit_code": None},
    )
    monkeypatch.setattr(orthonym_service, "_escalated_namer", _RecordingNamer())

    item = orthonym_service.translate_one("CCO", best_effort=True)

    assert called == ["CCO"], "the escalation never ran; best_effort=True is a no-op"
    assert item.status == "best_effort"
    assert item.name == "ethanol"


def test_a_verified_primary_pass_name_with_a_general_tier_prefix_is_a_fallback():
    """A measured fact the UI copy has to respect, pinned so it stays visible.

    A composer name that carries a general-tier ring prefix (source
    "pin_path") used to ship tier best_effort on the PRIMARY pass. Since engine
    eb25c33 ("honest tier labels", 2026-09-28) a verified one is
    pin_unverified, so status fallback; best_effort is kept for the
    last-resort floor and for a name no round trip verified. Over the first
    1,500 molecules of RDKit's NCI set the primary namer gave best_effort to
    none. Status best_effort with best-effort mode OFF now comes from this
    app's own demotion (no round trip here, or a failed one). If the engine
    moves this again, this test says so -- update the comments in
    orthonym_service.py and CLAUDE.md with it.
    """
    item = orthonym_service.translate_one(
        "OC(=O)CC12CC3CC(O)(CC(C3)C1)C2", best_effort=False
    )
    assert (item.status, item.tier) == ("fallback", "pin_unverified"), item
    assert item.roundtrip_match is True


# --- a verified status must not ship without its proof ---------------------


def test_a_pin_is_downgraded_when_opsin_could_not_verify_it(monkeypatch):
    """C3-followup, the backend half.

    SELF-01 uses the same opsin_parse() as the visible round-trip check, so a
    null roundtrip_smiles on this "pin" row (ethanol: RDKit-readable, verify
    on) can only mean OPSIN was unreachable:
    SELF-01 failed OPEN and shipped an unverified candidate wearing a
    verified label. The cache already refuses to persist that row for 7 days
    (name_cache.put_cached), but it was still SERVED once, and the frontend
    renders "pin" with the double rule that means round-trip confirmed.

    Declining to cache a lie is not the same as declining to tell it.
    """
    monkeypatch.setattr(orthonym_service, "opsin_parse", lambda name: None)

    item = orthonym_service.translate_one("CCO", best_effort=True)

    assert item.roundtrip_smiles is None
    assert item.status == "best_effort", (
        f"served status={item.status!r} with no round-trip proof; that is a "
        "verified tier claiming a verification that never happened"
    )
    assert item.name is not None, "the name itself is real and must survive the downgrade"
    assert item.tier == "pin_verified", (
        "the demotion moves the status only; the tier stays the engine's own"
    )


def test_an_unverifiable_name_abstains_when_the_caller_refused_best_effort(
    monkeypatch,
):
    """The interaction between the two guards, which is the part that is easy
    to get wrong: downgrading an unprovable "pin" to "best_effort" would hand
    a best_effort row to a caller who passed best_effort=False
    precisely to refuse them. For that caller the honest answer is abstain.
    """
    monkeypatch.setattr(orthonym_service, "opsin_parse", lambda name: None)

    item = orthonym_service.translate_one("CCO", best_effort=False)

    assert item.status == "abstain", (
        f"served status={item.status!r} to a caller who refused best-effort "
        "names"
    )
    assert item.name is None
    # The settings withheld a name the engine HAD; marked so that the
    # frontend offers no "Report SMILES on GitHub" for it (lib/github.js).
    assert item.limit_code == "withheld_unchecked"


def test_a_pin_whose_round_trip_differs_is_demoted(monkeypatch):
    """The other way a verified label goes unbacked: the round trip RAN and
    OPSIN read the name back as a different molecule. The tile used to print
    "does not match" under the double rule that means "matches". Propanol
    stands in for OPSIN's answer, so ethanol's InChIKey cannot agree with it.
    """
    monkeypatch.setattr(orthonym_service, "opsin_parse", lambda name: "CCCO")

    item = orthonym_service.translate_one("CCO", best_effort=True)

    assert item.roundtrip_match is False
    assert item.status == "best_effort", (
        f"served status={item.status!r} beside a round trip that does not match"
    )
    assert item.name is not None, "the name is real and must survive the downgrade"
    assert item.tier == "pin_verified", "the tier stays the engine's own"


def test_a_mismatched_name_abstains_for_a_caller_who_refused_best_effort(
    monkeypatch,
):
    """Same interaction as the unverifiable case, one difference: this check
    RAN and failed, so the name is an engine defect worth reporting, and the
    abstain must not carry "withheld_unchecked" (which hides the report link).
    """
    monkeypatch.setattr(orthonym_service, "opsin_parse", lambda name: "CCCO")

    item = orthonym_service.translate_one("CCO", best_effort=False)

    assert item.status == "abstain"
    assert item.name is None
    assert item.limit_code != "withheld_unchecked"


def test_a_genuinely_verified_pin_is_untouched():
    """Vacuity guard: with OPSIN really available, a real pin stays a pin.
    Without this, downgrading everything unconditionally would pass every
    assertion above.
    """
    item = orthonym_service.translate_one("CCO", best_effort=True)

    assert item.status == "pin"
    assert item.roundtrip_smiles is not None
    assert item.roundtrip_match is True


def test_a_best_effort_name_is_not_downgraded_for_lacking_proof(monkeypatch):
    """best_effort is ALREADY the honest label for "a real name from the
    general engine" -- its status claims no round trip, so a null one is not
    a contradiction and must not push it to abstain. Only statuses that CLAIM
    verification (pin, fallback) are demoted.
    """
    monkeypatch.setattr(orthonym_service, "opsin_parse", lambda name: None)
    monkeypatch.setattr(
        orthonym_service._namer,
        "name_tiered",
        lambda smiles: {"tier": "best_effort", "name": "ethanol", "formula": None, "limit_code": None},
    )

    # best_effort=False on purpose: with True a wrongly demoted row lands on
    # the same status, so demoting every unproven row would go unnoticed.
    item = orthonym_service.translate_one("CCO", best_effort=False)

    assert item.status == "best_effort"
    assert item.name == "ethanol"


# --- pin_unverified: a verified name, preferred status not certified --------


def test_classify_maps_pin_unverified_to_fallback_and_keeps_the_tier():
    """Paper reviewer issue 2. pin_unverified is a PIN-form name only a
    breadth producer built: it round-trips, and only its preferred status is
    uncertified. It used to ship as best_effort, labelled "OPSIN did not
    confirm it" beside a passing round trip."""
    row = {"tier": "pin_unverified", "name": "ethanol"}
    assert orthonym_service.classify(row) == ("fallback", "ethanol", "pin_unverified")


def test_a_pin_unverified_name_ships_as_a_verified_fallback(monkeypatch):
    """End to end, on the PRIMARY pass (where the engine assigns it too):
    best_effort=False refuses the escalated general engine, and must not turn
    a pin_unverified name into a best_effort row either."""
    monkeypatch.setattr(
        orthonym_service._namer,
        "name_tiered",
        lambda smiles: {"tier": "pin_unverified", "name": "ethanol", "formula": None, "limit_code": None},
    )

    item = orthonym_service.translate_one("CCO", best_effort=False)

    assert item.status == "fallback"
    assert item.tier == "pin_unverified"
    assert item.roundtrip_match is True


def test_classify_reports_an_abstain_without_a_name():
    """An abstain row's own name, when set, is a failure placeholder such as
    "unknown organic compound". classify must drop it, or it surfaces as a
    real name."""
    row = {"tier": "abstain", "name": "unknown organic compound"}
    assert orthonym_service.classify(row) == ("abstain", None, "abstain")


# --- naming health vs /explain health are different questions --------------


def test_a_broken_reflection_shim_does_not_take_naming_offline(monkeypatch):
    """CC5: the worker stamped its health from opsin_trace.self_check(),
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
    # celery_app imports opsin_trace inside the function (it must not
    # start a JVM in the pre-fork parent), so patch the source module.
    from app import opsin_trace

    monkeypatch.setattr(opsin_trace, "self_check", lambda: False)

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
    from app import opsin_trace

    monkeypatch.setattr(opsin_trace, "self_check", lambda: True)

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


# --- the four examples Home advertises -------------------------------------


@pytest.mark.parametrize("example", EXAMPLES, ids=lambda e: e["expected_status"])
def test_every_advertised_example_still_produces_the_status_it_claims(example):
    """CC1-examples: main.EXAMPLES hardcodes four expected_status claims and
    NOTHING checked them -- `grep -rn "expected_status" backend/tests/
    backend/scripts/` returned zero hits.

    These four render as the example chips on Home, the site's most visible
    surface, each labelled with the tier it is supposed to demonstrate. The
    engine improving is enough to falsify one: the abstain example has
    already been replaced TWICE for exactly that reason, both times because
    the Orthonym engine got better and started naming a molecule that used to
    abstain.
    So these are known to drift, and until now nothing failed when they did.

    verify_opsin_live.py proved exactly one of the four, against its own
    private copy of the SMILES rather than against EXAMPLES itself.
    """
    from app.orthonym_service import translate_one

    result = translate_one(example["smiles"], best_effort=True)

    assert result.status == example["expected_status"], (
        f"Home advertises {example['label']!r} as {example['expected_status']!r} "
        f"but the engine now returns {result.status!r}. Either the engine "
        "changed and the example must be replaced (it has happened twice "
        "before), or something is wrong with the engine."
    )
