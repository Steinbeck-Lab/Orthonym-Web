"""The token categories come from regexes.xml inside the pinned OPSIN jar.

An installed engine carries no OPSIN source tree, so a lookup that still
expects one finds nothing, and every token silently keeps its one-letter
symbol. /explain then marks no suffix at all. This asserts the table loaded.
"""

from app.opsin_tokenizer import _SUFFIX_CATEGORIES, _load_symbol_table


def test_the_symbol_table_is_read_from_the_opsin_jar():
    table = _load_symbol_table()
    assert _SUFFIX_CATEGORIES <= set(table.values())


def test_each_category_sits_under_its_own_symbol():
    # Checking only that the category names appear among the values passes a
    # table with its symbols scrambled or its multiplier entry dropped, and
    # then every token is categorised wrongly while the table still "loads".
    table = _load_symbol_table()
    assert table["r"] == "diOrTri"
    assert table["s"] == "nonAcidStemSuffix"
    assert table["¥"] == "suffixesThatCanBeModifiedByAPrefix"
