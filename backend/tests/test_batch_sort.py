"""Ordering for a batch job's rows, across pages.

The property that matters is not "the list is sorted" -- it is that the sort
is TOTAL and stable, because the client pages through the result. A sort that
leaves two rows comparing equal can show one of them on page 1 and again on
page 2, and drop a third entirely.
"""

import pytest

from app.batch_sort import sort_rows


def row(index, status="pin", name=None, rt=None, match=None):
    return {
        "index": index,
        "status": status,
        "name": name,
        "roundtrip_smiles": rt,
        "roundtrip_match": match,
    }


def indices(rows):
    return [r["index"] for r in rows]


def test_tier_sorts_down_the_ladder_strongest_first():
    rows = [
        row(0, "error"),
        row(1, "pin"),
        row(2, "abstain"),
        row(3, "fallback"),
        row(4, "best_effort"),
    ]
    assert indices(sort_rows(rows, "tier")) == [1, 3, 4, 2, 0]


def test_tier_descending_still_leaves_ties_in_input_order():
    # The reason sort_rows makes two passes. A single compound key sorted
    # descending would reverse the tiebreak too, so "weakest tier first"
    # would silently also mean "last molecule first" inside each tier.
    rows = [row(i, "pin") for i in range(4)] + [row(i, "abstain") for i in range(4, 8)]
    # Handed over out of index order, so a sort that only trusts the input
    # order (no index tiebreak of its own) cannot pass by luck.
    rows = rows[::-1]
    out = sort_rows(rows, "tier", "desc")
    assert indices(out) == [4, 5, 6, 7, 0, 1, 2, 3]


def test_an_unknown_status_sorts_after_every_known_tier():
    # Not before `pin`, which is where a -1 from a failed .index() would put
    # it. A tier the frontend cannot draw must not lead the table.
    rows = [row(0, "something_new"), row(1, "error"), row(2, "pin")]
    assert indices(sort_rows(rows, "tier")) == [2, 1, 0]


def test_name_sorts_alphabetically_and_case_insensitively():
    # Capitals that a case-sensitive compare would file before every lowercase
    # name ("Zinc" < "aluminium" in ASCII), so only casefolding gives 1, 2, 0.
    rows = [row(0, name="Zinc"), row(1, name="aluminium"), row(2, name="Beryl")]
    assert indices(sort_rows(rows, "name")) == [1, 2, 0]


def test_unnamed_rows_sort_last_in_an_a_to_z_sort():
    # Substituting "" for a missing name would file every abstain at the TOP,
    # which reads as though the engine named them something empty.
    rows = [row(0, "abstain"), row(1, name="zzz"), row(2, "error"), row(3, name="aaa")]
    assert indices(sort_rows(rows, "name")) == [3, 1, 0, 2]


def test_unnamed_rows_stay_last_when_the_name_sort_is_reversed():
    # Reversing Z-A must not drag the nameless rows to the front: they are
    # not the "last name alphabetically", they have no name at all.
    rows = [row(0, "abstain"), row(1, name="zzz"), row(2, name="aaa"), row(3, "error")]
    out = sort_rows(rows, "name", "desc")
    assert indices(out) == [1, 2, 0, 3]


def test_roundtrip_groups_match_then_mismatch_then_unavailable_then_none():
    rows = [
        row(0, "best_effort"),                                  # never claimed one
        row(1, "pin", rt=None),                                 # claims one, none recorded
        row(2, "fallback", rt="CCO", match=False),              # ran, disagreed
        row(3, "pin", rt="CCO", match=True),                    # ran, agreed
    ]
    assert indices(sort_rows(rows, "roundtrip")) == [3, 2, 1, 0]


def test_a_verified_tier_with_no_roundtrip_is_not_grouped_with_one_that_never_claimed():
    # The distinction the batch table already draws as "unavailable" vs "—".
    # Folding them together would hide a pin whose check was never recorded
    # among rows that never asserted a check at all.
    unavailable = row(0, "pin", rt=None)
    never = row(1, "best_effort", rt=None)
    out = sort_rows([never, unavailable], "roundtrip")
    assert indices(out) == [0, 1]


def test_index_sort_is_the_identity_on_already_ordered_rows():
    rows = [row(i) for i in range(5)]
    assert indices(sort_rows(rows, "index")) == [0, 1, 2, 3, 4]
    assert indices(sort_rows(rows, "index", "desc")) == [4, 3, 2, 1, 0]


def test_every_sort_is_a_total_order_so_paging_cannot_repeat_or_drop_a_row():
    # The paging property, asserted directly: slice the sorted list into
    # pages of 3 and demand the concatenation be a permutation of the input.
    rows = [
        row(0, "pin", name="b", rt="CCO", match=True),
        row(1, "pin", name="b", rt="CCO", match=True),
        row(2, "pin", name="b", rt="CCO", match=True),
        row(3, "abstain"),
        row(4, "abstain"),
        row(5, "error"),
        row(6, "error"),
    ]
    # Shuffled: rows already in index order make every stable sort look total.
    rows = [rows[i] for i in (4, 1, 6, 0, 5, 3, 2)]
    for field in ("index", "tier", "name", "roundtrip"):
        for order in ("asc", "desc"):
            out = sort_rows(rows, field, order)
            ties = [r["index"] for r in out]
            if field != "index":
                # Rows that compare equal on the field stay in index order.
                for a, b in zip(out, out[1:]):
                    if all(a[k] == b[k] for k in ("status", "name", "roundtrip_smiles", "roundtrip_match")):
                        assert a["index"] < b["index"], (field, order, ties)
            paged = [r for start in range(0, len(out), 3) for r in out[start : start + 3]]
            assert sorted(indices(paged)) == list(range(7)), (field, order)
            assert indices(paged) == indices(out), (field, order)


def test_sort_rows_leaves_the_caller_s_list_alone():
    # The endpoint passes a freshly materialised list, but a sort that
    # mutated its argument would be a trap for any future caller that reused
    # one.
    rows = [row(2), row(0), row(1)]
    sort_rows(rows, "index")
    assert indices(rows) == [2, 0, 1]


def test_an_unknown_sort_field_is_refused_rather_than_ignored():
    # Silently falling back to input order would answer a sort request with
    # unsorted rows and look like the sort simply did nothing.
    with pytest.raises(ValueError, match="unknown sort field"):
        sort_rows([row(0)], "smiles")
