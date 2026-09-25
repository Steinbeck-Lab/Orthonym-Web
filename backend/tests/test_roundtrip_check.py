"""The visible round-trip proof compares FULL INCHIKEYS, and it matters which.

This is the check whose verdict sits under every named result ("round-trip
check: ... matches"), and whose absence demotes a verified status. It used to
compare canonical SMILES, which cried wolf on an ordinary molecule:
zwitterionic glycine is correctly named "glycine", OPSIN reads that name back
as the neutral form, the two canonical SMILES differ, and a correct PIN was
therefore shipped displaying a MISMATCH.

The tests below pin both directions, because getting one right is easy:
  * a name describing a DIFFERENT compound must not pass -- including a
    stereo inversion, which the InChIKey *skeleton block* would have missed;
  * a name describing the SAME compound must not fail -- including when the
    protonation state differs, which is what InChI normalises away.

These hit the real OPSIN jar through the same in-process JVM the service uses,
so they need the environment backend/scripts/run-tests.sh sets up.
"""

import pytest
from rdkit import Chem

from app.orthonym_service import _roundtrip_check


def _check(name: str, smiles: str):
    mol = Chem.MolFromSmiles(smiles)
    assert mol is not None, f"test input {smiles!r} is not parseable"
    return _roundtrip_check(name, mol)


# --- fail-closed: a name for a different compound must not pass -----------


@pytest.mark.parametrize(
    ("name", "smiles", "why"),
    [
        ("ethanol", "CCC", "a name for an entirely different compound"),
        (
            "(2R)-butan-2-ol",
            "C[C@H](O)CC",
            "a STEREO INVERSION: the input is (2S). The InChIKey skeleton "
            "block is identical for both enantiomers, so a skeleton-only "
            "comparison would call this a match -- the full key must not",
        ),
        ("prop-1-en-2-ol", "CC(=O)C", "an enol name for a ketone"),
        ("benzene", "c1ccncc1", "a carbocycle's name for a pyridine"),
    ],
)
def test_a_name_for_another_compound_does_not_round_trip(name, smiles, why):
    roundtrip_smiles, match = _check(name, smiles)
    assert roundtrip_smiles, f"OPSIN should have parsed {name!r} ({why})"
    assert match is False, (
        f"{name!r} vs {smiles} was reported as a passing round trip, but {why}. "
        "A verified tier's rule claims this check succeeded."
    )


# --- and the true ones must stay true ------------------------------------


def test_a_protonation_difference_is_still_the_same_compound():
    """The case that prompted the change, kept as a regression.

    `[NH3+]CC(=O)[O-]` is glycine. OPSIN reads "glycine" back as `NCC(=O)O`.
    Different canonical SMILES, same compound -- InChI normalises the
    zwitterion -- so this must NOT be reported as a failed round trip.
    """
    roundtrip_smiles, match = _check("glycine", "[NH3+]CC(=O)[O-]")
    assert roundtrip_smiles, "OPSIN should parse 'glycine'"
    assert Chem.MolToSmiles(Chem.MolFromSmiles(roundtrip_smiles)) != Chem.MolToSmiles(
        Chem.MolFromSmiles("[NH3+]CC(=O)[O-]")
    ), (
        "this test is only meaningful while OPSIN returns a DIFFERENT "
        "canonical SMILES for glycine; if that changed, the false-alarm this "
        "guards against cannot occur and the test is no longer testing it"
    )
    assert match is True, (
        "a protonation difference was reported as a failed round trip -- the "
        "regression this check exists to prevent"
    )


@pytest.mark.parametrize(
    ("name", "smiles"),
    [
        ("ethanol", "CCO"),
        ("(2S)-butan-2-ol", "C[C@H](O)CC"),
        ("benzene", "c1ccccc1"),
        ("acetic acid", "CC(=O)O"),
    ],
)
def test_a_correct_name_round_trips(name, smiles):
    roundtrip_smiles, match = _check(name, smiles)
    assert roundtrip_smiles, f"OPSIN should parse {name!r}"
    assert match is True, f"{name!r} should round-trip to {smiles}"


def test_an_unparseable_name_reports_unavailable_not_mismatch():
    """(None, None), not (something, False).

    The difference is load-bearing: a null round trip means OPSIN could not
    answer, and orthonym_service demotes a verified status on exactly that
    signal. Reporting it as a mismatch instead would leave the verified label
    in place.
    """
    roundtrip_smiles, match = _check("not-a-chemical-name-at-all", "CCO")
    assert roundtrip_smiles is None
    assert match is None
