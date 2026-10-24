"""Name check: does a claimed name describe a structure?"""

from rdkit import Chem

from app.name_check import VERDICT_TEXT, compare_keys


def _key(smiles):
    return Chem.MolToInchiKey(Chem.MolFromSmiles(smiles))


def test_the_same_molecule_is_the_same_structure():
    assert compare_keys(_key("CCO"), _key("OCC")) == "same"


def test_mirror_images_share_a_skeleton_only():
    assert compare_keys(_key("C[C@@H](C(=O)O)N"), _key("C[C@H](C(=O)O)N")) == "stereo"


def test_a_zwitterion_is_the_same_structure_to_inchi():
    # Measured: standard InChI moves the zwitterion's protons back, so
    # L-alanine and its zwitterion share all three key blocks.
    assert compare_keys(_key("C[C@@H](C(=O)O)N"), _key("C[C@@H](C(=O)[O-])[NH3+]")) == "same"


def test_a_charged_form_differs_only_in_protonation():
    # Acetate vs acetic acid: the last block (protonation) differs.
    assert compare_keys(_key("CC(=O)O"), _key("CC(=O)[O-]")) == "protonation"


def test_different_molecules_are_different():
    assert compare_keys(_key("CCO"), _key("CO")) == "different"


def test_a_missing_key_cannot_be_compared():
    assert compare_keys(_key("CCO"), None) == "uncomparable"
    assert compare_keys(None, _key("CCO")) == "uncomparable"


def test_every_verdict_has_its_words():
    assert VERDICT_TEXT == {
        "same": "Same structure",
        "protonation": "Same skeleton; protonation differs",
        "stereo": "Same skeleton; stereo or isotopes differ",
        "different": "Different structure",
        "unreadable": "OPSIN cannot read this name",
        "uncomparable": "Could not compare",
    }
