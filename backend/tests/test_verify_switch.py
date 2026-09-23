"""The OPSIN-verify switch, and the one guarantee it has to keep.

The switch exists so a visitor can turn the proof OFF and watch every claim
downgrade -- PRODUCT.md principle 1 says determinism must be provable, and
being able to remove the proof and see it matter demonstrates that better than
a paragraph. The whole risk is the opposite outcome: a name that ships looking
verified when nothing verified it. Every test here is aimed at that.

Fail-closed in BOTH directions is the rule this file follows: it is not enough
that verify=False refuses to claim verification, the verify=True case must also
still EARN it, or the switch could be broken to "never verify" and half these
tests would still pass.
"""

from __future__ import annotations

import pytest

from app import name_cache
from app.orthonym_service import translate_one
from app.schemas import VERIFIED_STATUSES

# Two molecules the engine names and verifies cleanly. If either ever stops
# coming back "pin" with verification ON, the ON half of every pairing below
# is vacuous -- which is what test_the_premise_still_holds guards.
VERIFIABLE = ["CCO", "CC(=O)Oc1ccccc1C(=O)O"]


def test_the_premise_still_holds():
    """With verification ON these molecules really do reach a verified tier."""
    for smiles in VERIFIABLE:
        item = translate_one(smiles, verify=True)
        assert item.status in VERIFIED_STATUSES, f"{smiles} no longer verifies"
        assert item.roundtrip_smiles is not None
        assert item.roundtrip_match is True


@pytest.mark.parametrize("smiles", VERIFIABLE)
def test_verification_off_cannot_ship_a_verified_status(smiles):
    """The guarantee. No round trip ran, so no row may claim one did."""
    item = translate_one(smiles, verify=False)
    assert item.status not in VERIFIED_STATUSES
    assert item.status == "best_effort"


@pytest.mark.parametrize("smiles", VERIFIABLE)
def test_verification_off_shows_no_proof_it_does_not_have(smiles):
    """(None, None), not (something, False).

    A False match would read as "checked, and it disagreed" -- a different and
    much worse claim than "not checked".
    """
    item = translate_one(smiles, verify=False)
    assert item.roundtrip_smiles is None
    assert item.roundtrip_match is None


@pytest.mark.parametrize("smiles", VERIFIABLE)
def test_the_tier_moves_with_the_status(smiles):
    """Both fields of the payload must tell the same story.

    `status` is what the UI draws; `tier` is what an API or CSV consumer reads.
    Shipping status="best_effort" alongside tier="pin_verified" is the
    conflation PRODUCT.md principle 3 forbids, in the field nobody looks at.
    """
    item = translate_one(smiles, verify=False)
    assert item.tier != "pin_verified"
    assert item.tier in ("pin_unverified", "best_effort")


@pytest.mark.parametrize("smiles", VERIFIABLE)
def test_the_name_itself_is_unchanged(smiles):
    """Verification checks a name; it does not produce one.

    If the two differed, the switch would be changing the chemistry rather than
    the claim about it, and no downgrade could make that honest.
    """
    assert translate_one(smiles, verify=True).name == translate_one(
        smiles, verify=False
    ).name


def test_strict_mode_refuses_rather_than_downgrades():
    """best_effort=False + verify=False is a contradiction, resolved honestly.

    That caller refused OPSIN-unverified names outright. Handing them a
    downgraded best_effort row would reintroduce through the back door exactly
    what their flag keeps out the front, so the answer is an abstain.
    """
    item = translate_one(VERIFIABLE[0], best_effort=False, verify=False)
    assert item.status == "abstain"
    assert item.name is None


class TestCacheSeparation:
    """A verified and an unverified run must never share a cache entry.

    They are not equivalent: the unverified row is strictly weaker. One
    unverified request sharing the key would poison the entry for the full
    7-day TTL, and every later caller who ASKED for verification would be told
    their molecule could not be verified.
    """

    def test_the_key_carries_the_flag(self):
        assert name_cache.cache_key("CCO", True, True) != name_cache.cache_key(
            "CCO", True, False
        )

    def test_best_effort_is_still_in_the_key(self):
        """The pre-existing separation must survive the new flag."""
        assert name_cache.cache_key("CCO", True, True) != name_cache.cache_key(
            "CCO", False, True
        )

    def test_the_same_flags_still_hit(self):
        """Fail-closed the other way: the key must be STABLE, not just unique.

        A key that varied per call would separate everything and cache nothing.
        """
        assert name_cache.cache_key("CCO", True, False) == name_cache.cache_key(
            "CCO", True, False
        )


def test_default_is_verification_on():
    """The switch ships ON. A caller that says nothing gets the proof.

    Checked on the function default rather than through the API, because this
    is the value every internal caller inherits too -- including a Celery task
    message enqueued before the flag existed, which carries no argument for it.
    """
    import inspect

    assert inspect.signature(translate_one).parameters["verify"].default is True
    assert inspect.signature(name_cache.cache_key).parameters["verify"].default is True

    from app.schemas import TranslateRequest

    assert TranslateRequest(smiles=["CCO"]).verify is True
