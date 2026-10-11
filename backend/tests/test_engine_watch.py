"""engine_watch's report: a change or a broken Home example must exit 1."""

from scripts.engine_watch import report

OLD = [
    {"id": "a", "smiles": "CCO", "status": "pin", "tier": "pin_verified", "name": "ethanol"},
    {"id": "b", "smiles": "CCC", "status": "pin", "tier": "pin_verified", "name": "propane"},
]


def test_an_unchanged_panel_reports_nothing():
    text, code = report("1.0.6", "1.0.6", OLD, [dict(r) for r in OLD], [])
    assert code == 0
    assert "0 of 2 molecules changed" in text


def test_a_changed_tier_is_listed_and_exits_1():
    new = [dict(OLD[0]), dict(OLD[1], status="fallback", tier="systematic_verified")]
    text, code = report("1.0.6", "1.0.7", OLD, new, [])
    assert code == 1
    assert "1 of 2 molecules changed" in text
    assert "| b | `CCC` | pin · propane | fallback · propane |" in text


def test_a_broken_home_example_exits_1_even_with_no_panel_change():
    text, code = report("1.0.6", "1.0.7", OLD, [dict(r) for r in OLD], ["Ethanol: advertised `pin`, engine returns `fallback`"])
    assert code == 1
    assert "Home examples that no longer match" in text
