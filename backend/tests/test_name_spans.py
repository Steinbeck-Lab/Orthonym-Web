from app.name_spans import compute_spans
from tests.conftest import CAFFEINE, GOLDEN_NAMES

# Document order: the methyl stem, the ring, then the suffix token.
CAFFEINE_GROUPS = ["meth", "purin", "one"]


def test_caffeine_part_spans_are_pinned_exactly():
    spans = compute_spans(CAFFEINE, CAFFEINE_GROUPS, want_modifier=True)
    assert spans is not None
    assert CAFFEINE[slice(*spans.parts["meth"])] == "1,3,7-trimethyl-"
    assert CAFFEINE[slice(*spans.parts["purin"])] == "purine"
    assert CAFFEINE[slice(*spans.parts["one"])] == "-2,6-dione"


def test_caffeine_spans_partition_the_whole_name_without_gaps():
    # The four parts should tile the name end to end. This is the strongest
    # single check that the growth rules are right: a stolen or dropped
    # character shows up here immediately.
    spans = compute_spans(CAFFEINE, CAFFEINE_GROUPS, want_modifier=True)
    ordered = sorted(spans.parts.values())
    assert ordered[0][0] == 0
    assert ordered[-1][1] == len(CAFFEINE)
    for (_, prev_end), (next_start, _) in zip(ordered, ordered[1:]):
        assert prev_end == next_start, f"gap or overlap at {prev_end}/{next_start}"


def test_caffeine_suffix_locants_are_pinned_and_distinct_from_the_methyls():
    spans = compute_spans(CAFFEINE, CAFFEINE_GROUPS, want_modifier=True)
    suffix = spans.locants["one"]
    assert CAFFEINE[slice(*suffix["2"])] == "2"
    assert CAFFEINE[slice(*suffix["6"])] == "6"
    assert suffix["2"][0] > spans.parts["purin"][1]


def test_caffeine_locant_spans_are_pinned_exactly():
    spans = compute_spans(CAFFEINE, CAFFEINE_GROUPS, want_modifier=True)
    assert spans.locants["meth"]["1"] == (0, 1)
    assert spans.locants["meth"]["3"] == (2, 3)
    assert spans.locants["meth"]["7"] == (4, 5)
    assert CAFFEINE[0:1] == "1"
    assert CAFFEINE[4:5] == "7"


def test_the_same_locant_in_two_places_gets_two_different_spans():
    # Caffeine's "3" appears in "1,3,7-" (the methyls) and again in "3,7-"
    # (the hydro prefix). They mean different things and must not share a
    # span -- a flat locant map would hand the modifier the methyls' letters.
    spans = compute_spans(CAFFEINE, CAFFEINE_GROUPS, want_modifier=True)
    methyl_3 = spans.locants["meth"]["3"]
    modifier_3 = spans.locants["__modifier__"]["3"]
    assert methyl_3 != modifier_3
    assert methyl_3 == (2, 3)
    assert CAFFEINE[slice(*modifier_3)] == "3"
    assert modifier_3[0] >= spans.parts["__modifier__"][0]


def test_each_locant_span_sits_inside_its_own_part():
    spans = compute_spans(CAFFEINE, CAFFEINE_GROUPS, want_modifier=True)
    for key, found in spans.locants.items():
        part_start, part_end = spans.parts[key]
        for locant, (start, end) in found.items():
            assert part_start <= start < end <= part_end, (
                f"{key}/{locant} span {(start, end)} escapes its part"
            )


def test_caffeine_modifier_span_covers_the_hydro_prefix():
    spans = compute_spans(CAFFEINE, CAFFEINE_GROUPS, want_modifier=True)
    text = CAFFEINE[slice(*spans.parts["__modifier__"])]
    assert "hydro" in text and "1H" in text


def test_every_span_slices_to_real_text_and_none_overlap():
    spans = compute_spans(CAFFEINE, CAFFEINE_GROUPS, want_modifier=True)
    ranges = sorted(spans.parts.values())
    for start, end in ranges:
        assert 0 <= start < end <= len(CAFFEINE)
    for (_, prev_end), (next_start, _) in zip(ranges, ranges[1:]):
        assert prev_end <= next_start, "part spans overlap"


def test_an_unknown_group_token_yields_no_spans_rather_than_a_guess():
    # "zzz" appears nowhere in the name. The whole result must be withheld.
    assert compute_spans(CAFFEINE, ["meth", "zzz"], want_modifier=False) is None


def test_a_name_the_tokenizer_cannot_reconstruct_yields_none():
    assert compute_spans("not a chemical name at all", ["meth"], False) is None


def test_no_group_tokens_yields_none_rather_than_an_empty_success():
    # An empty SpanSet would read as success to every caller and make the
    # coverage check vacuous.
    assert compute_spans(CAFFEINE, [], want_modifier=False) is None


def test_never_returns_a_span_that_does_not_contain_its_group_token():
    # The safety property, stated directly: whatever names DO produce spans,
    # each span must literally contain the token it was anchored on.
    for name in GOLDEN_NAMES:
        for groups in (["meth"], ["benzen"], ["prop"], ["eth"]):
            spans = compute_spans(name, groups, want_modifier=False)
            if spans is None:
                continue
            for group, (start, end) in spans.parts.items():
                if group == "__modifier__":
                    continue
                assert group in name[start:end], (
                    f"{name}: span for {group!r} is {name[start:end]!r}"
                )
