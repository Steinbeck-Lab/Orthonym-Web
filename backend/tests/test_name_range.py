from app.explain import explain_name
from tests.conftest import CAFFEINE, GOLDEN_NAMES


def test_caffeine_segments_carry_spans_that_slice_to_the_right_text():
    result = explain_name(CAFFEINE)
    name = result["name"]
    by_kind = {s["kind"]: s for s in result["segments"]}
    assert name[slice(*by_kind["substituent"]["name_range"])] == "1,3,7-trimethyl-"
    assert name[slice(*by_kind["parent"]["name_range"])] == "purine"


def test_caffeine_locant_children_carry_their_own_spans():
    result = explain_name(CAFFEINE)
    name = result["name"]
    methyl = next(s for s in result["segments"] if s["kind"] == "substituent")
    got = {c["locant"]: name[slice(*c["name_range"])] for c in methyl["children"]}
    assert got == {"1": "1", "3": "3", "7": "7"}


def test_spans_are_all_or_nothing_never_partial():
    # A response with some spans and some None would leave dead regions in
    # the name that look identical to unhovered ones.
    for name in GOLDEN_NAMES:
        result = explain_name(name)
        if result["error"]:
            continue
        present = [s["name_range"] is not None for s in result["segments"]]
        assert all(present) or not any(present), f"{name}: mixed spans {present}"


def test_every_span_lies_inside_the_name():
    for name in GOLDEN_NAMES:
        result = explain_name(name)
        if result["error"]:
            continue
        for segment in result["segments"]:
            if segment["name_range"] is None:
                continue
            start, end = segment["name_range"]
            assert 0 <= start < end <= len(result["name"])
            for child in segment["children"]:
                if child["name_range"] is None:
                    continue
                assert start <= child["name_range"][0] < child["name_range"][1] <= end


def test_caffeine_suffix_segment_and_its_locants_are_hoverable():
    result = explain_name(CAFFEINE)
    name = result["name"]
    suffix = next(s for s in result["segments"] if s["kind"] == "suffix")
    assert name[slice(*suffix["name_range"])] == "-2,6-dione"
    got = {c["locant"]: name[slice(*c["name_range"])] for c in suffix["children"]}
    assert got == {"2": "2", "6": "6"}


def test_the_repeated_locant_3_points_at_different_letters_per_part():
    # "3" appears in "1,3,7-" and again in "3,7-". The methyl child and the
    # modifier child must underline DIFFERENT characters.
    result = explain_name(CAFFEINE)
    by_kind = {s["kind"]: s for s in result["segments"]}
    methyl_3 = next(c for c in by_kind["substituent"]["children"] if c["locant"] == "3")
    modifier_3 = next(c for c in by_kind["modifier"]["children"] if c["locant"] == "3")
    assert methyl_3["name_range"] != modifier_3["name_range"]
