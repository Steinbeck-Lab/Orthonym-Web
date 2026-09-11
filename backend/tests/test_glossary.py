from app.glossary import describe_locant, describe_part


def test_known_substituent_gets_its_own_words():
    text = describe_part("substituent", "methyl", "1", 1)
    assert "CH3" in text
    assert "1" in text


def test_unknown_part_gets_a_neutral_factual_line_not_invented_prose():
    text = describe_part("substituent", "zzzql", None, 3)
    assert "zzzql" in text
    assert "3 atoms" in text


def test_suffix_describes_the_group():
    assert "C=O" in describe_part("suffix", "one", None, 2)


def test_parent_ring_is_named():
    assert "purin" in describe_part("parent", "purin", None, 9)


def test_known_parent_stem_gets_a_real_explanation():
    # OPSIN's <group> token for caffeine's core is the stem "purin", not
    # "purine". The glossary must still explain it in plain words.
    text = describe_part("parent", "purin", None, 9)
    assert "purine" in text
    assert "9 atoms" in text or "9" in text


def test_unknown_parent_stem_still_gets_a_neutral_line():
    text = describe_part("parent", "zzzql", None, 4)
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


def test_carbonyl_suffix_does_not_claim_it_is_a_ketone():
    # Caffeine's -dione carbonyls sit between ring nitrogens: amide-like,
    # not ketones. The glossary cannot tell from the suffix alone, so it
    # must not claim the stronger fact.
    text = describe_part("suffix", "dione", None, 2)
    assert "C=O" in text
    assert "ketone" not in text.lower()


def test_a_fusion_bracket_explains_what_it_does():
    from app.glossary import describe_token

    line = describe_token("fusionBracket", "[a]")
    assert line is not None
    assert "fuse" in line.lower()


def test_a_ring_assembly_multiplier_says_how_many():
    from app.glossary import describe_token

    line = describe_token("ringAssemblyMultiplier", "bi")
    assert line is not None
    assert "two" in line.lower()


def test_an_elision_vowel_teaches_nothing_and_gets_no_line():
    """A token child for the `e` of `pyrene` would be noise. None means the
    token gets a span for continuity but no explanation of its own.
    """
    from app.glossary import describe_token

    assert describe_token("e", "e") is None


def test_an_unknown_category_gets_no_line_rather_than_a_wrong_one():
    from app.glossary import describe_token

    assert describe_token("someCategoryOpsinAddedLater", "zzz") is None
