"""The census classifier is the yardstick every later task is measured with,
so it gets its own tests. A classifier that silently mislabels an outcome
would make every coverage number meaningless.
"""

from scripts.explain_census import SPAN_BEARING, classify


def _seg(kind, name_range=None, owns=True, atoms=(), children=()):
    return {
        "label": kind,
        "kind": kind,
        "owns_atoms": owns,
        "atom_indices": list(atoms),
        "name_range": name_range,
        "children": list(children),
    }


def test_an_engine_error_is_its_own_outcome_and_nothing_else():
    payload = {"error": "OPSIN could not parse this name.", "segments": []}
    assert classify(payload) == ["ENGINE_ERROR"]


def test_a_fully_spanned_name_is_clean():
    payload = {
        "error": None,
        "total_atoms": 2,
        "segments": [_seg("parent", name_range=[0, 7], atoms=(0, 1))],
    }
    assert classify(payload) == ["CLEAN"]


def test_a_name_with_no_span_at_all_is_spans_none():
    payload = {
        "error": None,
        "total_atoms": 2,
        "segments": [_seg("parent", name_range=None, atoms=(0, 1))],
    }
    assert "SPANS_NONE" in classify(payload)


def test_one_dead_child_locant_is_partial_not_clean():
    """Caffeine's own shape: the parent is spanned, one locant child is not.
    This must NOT read as clean -- it is the 130-name class.
    """
    payload = {
        "error": None,
        "total_atoms": 2,
        "segments": [
            _seg("parent", name_range=[0, 7], atoms=(0, 1), children=[
                _seg("suffix", name_range=[1, 2], owns=False),
                _seg("suffix", name_range=None, owns=False),
            ]),
        ],
    }
    assert classify(payload) == ["SPANS_PARTIAL"]


def test_an_uncovered_heavy_atom_is_an_atom_gap():
    payload = {
        "error": None,
        "total_atoms": 5,
        "segments": [_seg("parent", name_range=[0, 7], atoms=(0, 1))],
    }
    assert "ATOM_GAP" in classify(payload)


def test_modifier_counts_as_span_bearing():
    assert "modifier" in SPAN_BEARING
