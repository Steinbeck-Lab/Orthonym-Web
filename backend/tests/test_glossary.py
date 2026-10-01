from app.glossary import GENERIC_TOKEN_LINE, describe_locant, describe_part, describe_token


def test_known_substituent_gets_its_own_words():
    assert "CH3" in describe_part("substituent", "methyl", 1)


def test_unknown_part_gets_a_neutral_factual_line_not_invented_prose():
    text = describe_part("substituent", "zzzql", 3)
    assert "zzzql" in text
    assert "3 atoms" in text


def test_suffix_describes_the_group():
    assert "C=O" in describe_part("suffix", "one", 2)


def test_known_parent_stem_gets_a_real_explanation():
    # OPSIN's <group> token for caffeine's core is the stem "purin", not
    # "purine". The glossary must still explain it in plain words.
    text = describe_part("parent", "purin", 9)
    assert "purine" in text
    assert "9 atoms" in text or "9" in text


def test_unknown_parent_stem_still_gets_a_neutral_line():
    text = describe_part("parent", "zzzql", 4)
    assert "zzzql" in text
    assert "4 atoms" in text


def test_modifier_locant_may_name_the_atom_it_was_handed():
    # The ONE branch allowed to name an atom. explain.py resolves a modifier
    # locant against the PARENT skeleton's own atoms and hands over that
    # atom's real element, so caffeine's "1H" reads "the N1 atom".
    assert "N7" in describe_locant("modifier", "7", "N")


def test_substituent_and_suffix_locants_never_name_an_atom():
    # REPLACES test_locant_description_names_the_atom, which asserted
    #     assert "N7" in describe_locant("substituent", "7", "N")
    # That assertion encoded the defect rather than guarding against it. No
    # caller can supply a correct element for a substituent or suffix child,
    # and the element they DID supply produced fabricated atom labels,
    # verified live before this change:
    #   caffeine  "Position 1 - the C1 atom"          -> position 1 is N1
    #   caffeine  "Position 2 - hangs off O2"         -> it hangs off C2
    #   tryptophan "Position 2 - the N2 atom"         -> no N2 exists there
    # An element is passed in here deliberately: even when a caller hands one
    # over, these two branches must state the position ONLY and ignore it.
    for kind in ("substituent", "suffix"):
        text = describe_locant(kind, "7", "N")
        assert "7" in text, kind
        assert "N7" not in text, f"{kind} fabricated an atom label: {text!r}"
    # The two branches say different things: a suffix hangs off the parent
    # skeleton, a substituent is simply attached. A suffix line that fell
    # through to the bare "Position 7." would pass the loop above.
    assert "parent skeleton" in describe_locant("suffix", "7", "N")
    assert "parent skeleton" not in describe_locant("substituent", "7", "N")


def test_carbonyl_suffix_does_not_claim_it_is_a_ketone():
    # Caffeine's -dione carbonyls sit between ring nitrogens: amide-like,
    # not ketones. The glossary cannot tell from the suffix alone, so it
    # must not claim the stronger fact.
    text = describe_part("suffix", "dione", 2)
    assert "C=O" in text
    assert "ketone" not in text.lower()


def test_a_fusion_bracket_explains_what_it_does():
    from app.glossary import describe_token

    line = describe_token("fusion", "[a]")
    assert line is not None
    assert "fuse" in line.lower()


def test_a_ring_assembly_multiplier_says_how_many():
    from app.glossary import describe_token

    line = describe_token("ringAssemblyMultiplier", "bi")
    assert line is not None
    assert "two" in line.lower()


def test_a_ring_assembly_multiplier_counts_by_its_own_word():
    # "ter" (terphenyl) is three copies. A count fixed at two for every
    # multiplier word would still pass the "bi" case above.
    from app.glossary import describe_token

    assert "three" in describe_token("ringAssemblyMultiplier", "ter").lower()
    assert "two" not in describe_token("ringAssemblyMultiplier", "ter").lower()


def test_every_listed_token_category_gets_its_own_line():
    # A describe_token that answered every known category with one line
    # (the fusion-bracket sentence, say) passes the single-category cases
    # above. Each category's line must say what THAT token does.
    from app.glossary import describe_token

    expect = {
        "fusion": "fused",
        "multiplier": "how many",
        "hydro": "hydrogens were added",
        "indicatedHydrogen": "carries a hydrogen",
        "stereoChemistry": "three-dimensional",
        "vonBaeyer": "bridge",
        "spiro": "shared between two rings",
    }
    for category, phrase in expect.items():
        line = describe_token(category, "x")
        assert line is not None and phrase in line, (category, line)


def test_a_single_atom_part_is_not_pluralised():
    text = describe_part("substituent", "zzzql", 1)
    assert "1 atom " in text or text.rstrip(".").endswith("1 atom"), text
    assert "atoms" not in text


def test_an_elision_vowel_teaches_nothing_and_gets_no_line():
    """A token child for the `e` of `pyrene` would be noise. None means the
    token gets a span for continuity but no explanation of its own.
    """
    from app.glossary import describe_token

    assert describe_token("e", "e") is None


def test_an_unknown_category_gets_no_line_rather_than_a_wrong_one():
    from app.glossary import describe_token

    assert describe_token("someCategoryOpsinAddedLater", "zzz") is None


def test_parse_tree_kinds_have_lines():
    for kind, text in [("multiplier", "tri"), ("hydro", "hydro"), ("indicatedHydrogen", "1H-"),
                       ("stereoChemistry", "(2S)-"), ("vonBaeyer", "cyclo[2.2.1]"),
                       ("spiro", "spiro[4.5]"), ("fusion", "[a]")]:
        assert describe_token(kind, text), kind


def test_old_tokenizer_category_names_are_gone():
    for old in ("fusionBracket", "diOrTri", "bigCapitalH", "stereochemistryBracket", "spiroDescriptor"):
        assert describe_token(old, "x") is None, old


def test_copies_are_counted_in_the_line():
    assert "3 copies" in describe_part("substituent", "methyl", 3, copies=3)
    assert "copies" not in describe_part("substituent", "methyl", 1)


def test_a_written_parent_label_finds_its_stem():
    assert "two fused rings" in describe_part("parent", "purine", 9)
    assert "two-carbon" in describe_part("parent", "ethan", 2)


def test_a_ring_is_never_described_as_a_chain():
    assert "chain" not in describe_part("substituent", "cyclopropyl", 3)
    assert "chain" in describe_part("substituent", "2-methylpropyl", 4)


def test_an_anomeric_locant_has_its_own_line_only_for_a_sugar():
    assert "anomer" in describe_locant("position", "alpha", anomer=True)
    assert "anomer" in describe_locant("position", "beta", anomer=True)
    # "alpha,alpha,alpha-trifluorotoluene": a Greek position, not an anomer.
    assert "anomer" not in describe_locant("position", "alpha")
    assert "anomer" not in describe_locant("substituent", "alpha")
    assert describe_locant("position", "alpha") == "Position alpha."


# Each of these once got a confidently wrong line from the ending fallback.
WRONG = [
    ("suffix", "thiol", "-OH"),
    ("suffix", "esulfonic acid", "C(=O)OH"),
    ("suffix", "onate", "ester"),
    ("suffix", "sulfonamide", "C(=O)N"),
    ("suffix", "thione", "C=O"),
    ("suffix", "sulfinic acid", "C(=O)OH"),
    ("suffix", "phosphonate", "ester"),
    ("substituent", "phenoxy", "-O- linkage"),
    ("substituent", "cyclopropyl", "chain"),
    ("substituent", "thiomethyl", "CH3 group"),
]


def test_an_ending_that_merely_looks_like_a_known_one_gets_a_neutral_line():
    for kind, label, claim in WRONG:
        line = describe_part(kind, label, 3)
        assert claim not in line, (label, line)
        assert f'"{label}" covers 3 atoms' in line, (label, line)


def test_known_endings_and_counted_endings_still_say_what_they_are():
    assert "C=O" in describe_part("suffix", "dione", 2)
    assert "-OH" in describe_part("suffix", "triol", 3)
    assert "nitrogen" in describe_part("suffix", "diamine", 2)
    assert "-C(=O)OH" in describe_part("suffix", "oic acid", 3)
    assert "-C(=O)OH" in describe_part("suffix", "dicarboxylic acid", 4)
    assert "C≡N" in describe_part("suffix", "onitrile", 2)
    assert "-C(=O)N-" in describe_part("suffix", "dicarboxamide", 6)
    assert "ester" in describe_part("suffix", "dicarboxylate", 6)
    assert "four-carbon" in describe_part("substituent", "tert-butyl", 4)
    assert "three-carbon" in describe_part("substituent", "isopropyl", 3)
    assert "-O-CH3" in describe_part("substituent", "methoxy", 2)


def test_generic_token_line_names_the_text():
    assert "zzz" in GENERIC_TOKEN_LINE.format(text="zzz")


# -- final review: M1, M2, M5, I3 (glossary level) ------------------------------------

def test_one_atom_is_not_one_atoms():
    from app.glossary import describe_functional
    assert "1 atom." in describe_part("parent", "zzzql", 1)
    assert "1 atom." in describe_part("parent", "purin", 1)
    assert "1 atoms" not in describe_part("substituent", "zzzql", 1)
    assert "1 atoms" not in describe_functional("zzz", 1)


def test_the_parent_prose_is_used_only_when_the_atom_count_fits_the_stem():
    assert "two-carbon" in describe_part("parent", "acet", 2)
    assert "two-carbon" not in describe_part("parent", "acet", 8)      # acetophenone
    assert "benzene ring" not in describe_part("parent", "benz", 12)    # benzophenone
    assert "benzene ring" in describe_part("parent", "benz", 12, copies=2)   # two benzene rings
    assert "core skeleton" in describe_part("parent", "acet", 8)


def test_a_suffix_line_needs_atoms_that_bear_it_out():
    from rdkit import Chem
    from app.glossary import suffix_claim, suffix_claim_holds
    acid = Chem.MolFromSmiles("CC(=O)O")
    ester = Chem.MolFromSmiles("CC(=O)OC")
    salt = Chem.MolFromSmiles("CC(=O)[O-]")
    hydrazide = Chem.MolFromSmiles("CC(=O)NN")
    assert suffix_claim("oic acid") == "acid" and suffix_claim("one") == "carbonyl" and suffix_claim("ol") is None
    assert suffix_claim_holds("oic acid", acid, [2, 3]) and suffix_claim_holds("oic acid", salt, [2, 3])
    assert not suffix_claim_holds("oic acid", ester, [2, 3])
    assert not suffix_claim_holds("oic acid", hydrazide, [2])
    assert suffix_claim_holds("ate", ester, [2, 3]) and suffix_claim_holds("ate", salt, [2, 3])
    assert not suffix_claim_holds("ate", hydrazide, [2])
    assert suffix_claim_holds("one", Chem.MolFromSmiles("CC(=O)C"), [2])
    assert not suffix_claim_holds("one", Chem.MolFromSmiles("CC(=NO)C"), [4, 5])
    assert not suffix_claim_holds("oic acid", None, [2])              # no molecule: neutral, never a guess
    assert suffix_claim_holds("ol", None, [0])                         # no claim to check
    assert "covers 2 atoms" in describe_part("suffix", "oic acid", 2, holds=False)


def test_a_functional_word_line_is_used_only_for_the_atoms_the_word_adds():
    from app.glossary import describe_functional
    assert "C=O" in describe_functional("ketone", 2)
    assert "C=O" not in describe_functional("ketone", 3)
    assert "adds" not in describe_functional("ester", 0) and "no atoms of its own" in describe_functional("ester", 0)
    assert "covers 6 atoms" in describe_functional("hexafluoride", 6)


def test_the_glossary_has_no_branch_nothing_can_reach():
    # describe_locant("unmapped") and describe_part("modifier") were unreachable in v2
    assert describe_locant("unmapped", "7") == "Position 7."
    assert "does not add atoms" not in describe_part("modifier", "7", 1)
