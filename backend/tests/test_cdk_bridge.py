"""CDK: the second SMILES parser and the default depiction engine.

Every test here asserts on the ANSWER, not on the absence of an exception.
`cdk_bridge` is built to swallow failures and return None, so a test that only
checked "did not raise" would pass just as happily against a CDK that had
stopped loading entirely -- which is precisely the regression these guard.

The two SVG engines are told apart by a marker only one of them writes:
RDKit declares `xmlns:rdkit`, CDK writes a `<!DOCTYPE svg PUBLIC` line.
"""

from __future__ import annotations

import base64

import pytest
from rdkit import Chem

from app import cdk_bridge
from app.depiction import structure_svg_data_uri
from app.inputs import _canonical_or_error

# RDKit rejects these; CDK reads them. Verified against both toolkits rather
# than assumed -- test_the_premise_still_holds below fails if that stops being
# true, because every other test in this file would then be vacuous.
RDKIT_REJECTS_CDK_ACCEPTS = "CN(C)(C)C"

# Neither toolkit can make sense of this one.
NEITHER_TOOLKIT_ACCEPTS = "c1ccc2c(c1)c1ccccc1n2=O"


def _svg_of(data_uri: str) -> str:
    assert data_uri.startswith("data:image/svg+xml;base64,")
    return base64.b64decode(data_uri.split(",", 1)[1]).decode("utf-8")


def _engine_of(data_uri: str) -> str:
    svg = _svg_of(data_uri)
    if "xmlns:rdkit" in svg:
        return "rdkit"
    if "<!DOCTYPE svg PUBLIC" in svg:
        return "cdk"
    return "unknown"


def test_the_premise_still_holds():
    """The fixtures are what this whole module is about; assert them directly.

    If RDKit ever starts accepting RDKIT_REJECTS_CDK_ACCEPTS, the fallback
    tests below would still pass while testing nothing at all.
    """
    assert Chem.MolFromSmiles(RDKIT_REJECTS_CDK_ACCEPTS) is None
    assert cdk_bridge.parse_smiles(RDKIT_REJECTS_CDK_ACCEPTS) is not None
    assert Chem.MolFromSmiles(NEITHER_TOOLKIT_ACCEPTS) is None
    assert cdk_bridge.parse_smiles(NEITHER_TOOLKIT_ACCEPTS) is None


def test_cdk_is_available_in_this_process():
    """The isolated classloader loads, in a plain process with no Celery.

    Fail-closed in both directions: this is the "good case still allowed" half.
    Without it, every fallback test below would pass by falling back.
    """
    assert cdk_bridge.available() is True
    assert cdk_bridge.self_check() is True


@pytest.mark.parametrize(
    "smiles,expected",
    [
        ("C[C@H](N)C(=O)O", ["S"]),  # L-alanine
        ("C[C@@H](N)C(=O)O", ["R"]),  # D-alanine
        ("C/C=C/C", ["E"]),  # (E)-but-2-ene
        ("C/C=C\\C", ["Z"]),  # (Z)-but-2-ene
        ("CCO", []),  # nothing stereogenic to report
    ],
)
def test_cip_labels_are_correct(smiles, expected):
    """The CIP half is the reason CDK is the default renderer at all.

    The labels are drawn as glyph PATHS in the SVG, so searching the rendered
    output for "S" would find nothing. cdk_bridge.cip_labels reads them off the
    annotated molecule, which is the only way this is testable.
    """
    assert cdk_bridge.cip_labels(smiles) == expected


def test_an_undefined_stereocentre_is_marked_not_hidden():
    """A real but unspecified centre must read as unspecified.

    Alanine written without the @ is a genuine stereocentre whose configuration
    the input does not state. Drawing it as though it were settled is the exact
    kind of overstatement PRODUCT.md principle 2 forbids.
    """
    assert cdk_bridge.cip_labels("CC(N)C(=O)O") == ["(?)"]


def test_cdk_draws_what_rdkit_cannot_parse():
    svg = cdk_bridge.depict_svg(RDKIT_REJECTS_CDK_ACCEPTS, 240, 180)
    assert svg is not None
    assert svg.lstrip().startswith("<")
    assert "<!DOCTYPE svg PUBLIC" in svg


def test_cdk_declines_what_it_cannot_read():
    assert cdk_bridge.depict_svg(NEITHER_TOOLKIT_ACCEPTS, 240, 180) is None
    assert cdk_bridge.normalise_smiles(NEITHER_TOOLKIT_ACCEPTS) is None
    assert cdk_bridge.depict_svg("", 240, 180) is None
    assert cdk_bridge.parse_smiles("") is None


class TestDepictionEnginePreference:
    """CDK draws by default; RDKit only when CDK cannot."""

    def test_cdk_wins_when_both_could_draw(self):
        mol = Chem.MolFromSmiles("CCO")
        assert mol is not None
        uri = structure_svg_data_uri("CCO", mol)
        assert _engine_of(uri) == "cdk"

    def test_rdkit_draws_when_cdk_is_absent(self, monkeypatch):
        """The web-process case: no JVM, so no CDK, but still a picture.

        The fail-closed pair to the test above. A depiction module that had
        quietly lost its RDKit path would pass every other test in this file.
        """
        monkeypatch.setattr(cdk_bridge, "depict_svg", lambda *a, **k: None)
        mol = Chem.MolFromSmiles("CCO")
        uri = structure_svg_data_uri("CCO", mol)
        assert _engine_of(uri) == "rdkit"

    def test_no_engine_and_no_mol_gives_none_not_a_broken_picture(self, monkeypatch):
        monkeypatch.setattr(cdk_bridge, "depict_svg", lambda *a, **k: None)
        assert structure_svg_data_uri("CCO", None) is None
        assert structure_svg_data_uri(None, None) is None

    def test_a_mol_alone_still_draws(self):
        """Callers that hold only an RDKit Mol keep working."""
        uri = structure_svg_data_uri(None, Chem.MolFromSmiles("CCO"))
        assert _engine_of(uri) == "rdkit"


class TestCanonicalisationFallback:
    """app.inputs is the gate EVERY naming path passes through first.

    A fallback added only to orthonym_service.translate_one would be
    unreachable, because _canonical_or_error turns the molecule into an error
    row before the namer is ever asked. These tests are what pin that down.
    """

    def test_rdkit_rejected_smiles_survives_canonicalisation(self):
        parsed = _canonical_or_error(0, "row", RDKIT_REJECTS_CDK_ACCEPTS, None)
        assert parsed.error is None
        assert parsed.smiles is not None

    def test_unreadable_smiles_is_still_an_error(self):
        """Fail-closed: CDK must not turn nonsense into a molecule."""
        parsed = _canonical_or_error(0, "row", NEITHER_TOOLKIT_ACCEPTS, None)
        assert parsed.smiles is None
        assert parsed.error == "Could not parse this SMILES string"

    def test_rdkit_still_owns_the_normal_case(self, monkeypatch):
        """CDK must not be consulted for a SMILES RDKit accepted.

        Every molecule the site names would otherwise pay a JVM round trip.
        """
        def explode(*a, **k):  # pragma: no cover - the point is it never runs
            raise AssertionError("CDK was consulted for a SMILES RDKit accepted")

        monkeypatch.setattr(cdk_bridge, "normalise_smiles", explode)
        parsed = _canonical_or_error(0, "row", "CCO", None)
        assert parsed.smiles == "CCO"
        assert parsed.error is None

    def test_the_length_bound_still_runs_first(self, monkeypatch):
        """An oversized string must not reach either toolkit."""
        def explode(*a, **k):  # pragma: no cover
            raise AssertionError("a toolkit was called on an oversized SMILES")

        monkeypatch.setattr(cdk_bridge, "normalise_smiles", explode)
        parsed = _canonical_or_error(0, "row", "C" * 2001, None)
        assert parsed.smiles is None
        assert "exceeds" in parsed.error


def test_a_cdk_only_structure_gets_a_verdict_not_a_parse_error():
    """The user-visible payoff: "I read it and declined" beats "unparseable".

    Measured: this molecule abstains, and an abstain carries no depiction by
    design (_abstain_item), so what changes is the VERDICT. Asserting the
    measured status rather than accepting either branch is the point -- a
    version of this test that allowed both would still pass if the CDK gate
    were deleted and the row went back to being an error... except that it
    would not, which is what the second assertion pins down.
    """
    from app.orthonym_service import translate_one

    item = translate_one(RDKIT_REJECTS_CDK_ACCEPTS)
    assert item.status == "abstain"
    assert item.error is None
    assert item.name is None


def test_a_named_cdk_only_structure_cannot_claim_verification(monkeypatch):
    """No RDKit Mol means no round trip, so no verified tier may ship.

    Forced rather than waited for: no real molecule currently reaches this
    branch, but the branch exists and SELF-01 fails OPEN, so an untested path
    to a "pin" badge is exactly the failure this repo has shipped before.
    """
    from app import orthonym_service

    class _Namer:
        def name_tiered(self, smiles):
            return {"name": "trimethylazanium", "tier": "pin_verified"}

    monkeypatch.setattr(orthonym_service, "_namer", _Namer())
    monkeypatch.setattr(orthonym_service, "_escalated_namer", _Namer())

    item = orthonym_service.translate_one(RDKIT_REJECTS_CDK_ACCEPTS)
    assert item.name == "trimethylazanium"
    assert item.roundtrip_smiles is None
    assert item.roundtrip_match is None
    assert item.status == "best_effort", "a pin badge requires a real round trip"
    assert item.depiction_svg is not None
    assert _engine_of(item.depiction_svg) == "cdk"


def test_a_named_cdk_only_structure_is_refused_when_best_effort_is_off(monkeypatch):
    """Fail-closed pair: a caller who refused unverified names gets an abstain."""
    from app import orthonym_service

    class _Namer:
        def name_tiered(self, smiles):
            return {"name": "trimethylazanium", "tier": "pin_verified"}

    monkeypatch.setattr(orthonym_service, "_namer", _Namer())
    monkeypatch.setattr(orthonym_service, "_escalated_namer", _Namer())

    item = orthonym_service.translate_one(RDKIT_REJECTS_CDK_ACCEPTS, best_effort=False)
    assert item.status == "abstain"
    assert item.name is None


def test_truly_unparseable_smiles_is_still_an_error():
    """Fail-closed: CDK must not launder nonsense into a result."""
    from app.orthonym_service import translate_one

    item = translate_one(NEITHER_TOOLKIT_ACCEPTS)
    assert item.status == "error"
    assert item.error == "Could not parse this SMILES string"
    assert item.depiction_svg is None


def test_atom_count_matches_what_the_dos_bound_expects():
    """/api/depict bounds coordinate-generation cost with this number."""
    mol = cdk_bridge.parse_smiles("CN1C=NC2=C1C(=O)N(C)C(=O)N2C")  # caffeine
    assert cdk_bridge.atom_count(mol) == 14
    assert cdk_bridge.atom_count(None) == 0
