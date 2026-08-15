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


def test_locant_description_names_the_atom():
    assert "N7" in describe_locant("substituent", "7", "N")
