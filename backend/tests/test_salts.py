"""Opt-in salt stripping: name the largest organic fragment, say what went."""

from rdkit import Chem

from app.salts import strip_salts


def test_one_fragment_is_unchanged():
    assert strip_salts("CCO") == ("CCO", None)


def test_the_typed_text_of_the_kept_fragment_is_named():
    assert strip_salts("CC(=O)Oc1ccccc1C(=O)O.Cl") == ("CC(=O)Oc1ccccc1C(=O)O", "Cl")


def test_the_typed_order_is_kept():
    assert strip_salts("Cl.OCC") == ("OCC", "Cl")


def test_every_removed_fragment_is_listed():
    assert strip_salts("CCO.Cl.Cl") == ("CCO", "Cl.Cl")


def test_an_all_inorganic_salt_keeps_one_fragment():
    kept, removed = strip_salts("[Na+].[Cl-]")
    assert kept and removed
    assert {kept, removed} == {"[Na+]", "[Cl-]"}


def test_one_molecule_written_across_a_dot_is_not_split():
    # A ring-closure digit joins the two pieces: RDKit sees one fragment.
    assert strip_salts("C1.C1") == ("C1.C1", None)


def test_pieces_that_do_not_parse_alone_fall_back_to_canonical():
    # Ethane written across a dot, plus HCl: two fragments, but "C1" alone
    # is not a SMILES, so the kept text is RDKit's canonical form.
    kept, removed = strip_salts("C1.C1.Cl")
    assert (kept, removed) == ("CC", "Cl")
    assert Chem.MolFromSmiles(kept) is not None
