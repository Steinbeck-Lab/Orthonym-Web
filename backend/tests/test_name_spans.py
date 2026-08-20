from app.name_spans import MODIFIER_KEY, _locant_subspans, compute_spans
from app.opsin_tokenizer import Token
from tests.conftest import CAFFEINE, GOLDEN_NAMES

# Document order: the methyl stem, the ring, then the suffix token.
# `compute_spans` keys its result by POSITION in this list (0, 1, 2, ...),
# not by text -- see the ibuprofen tests below for why a text key is unsafe.
CAFFEINE_GROUPS = ["meth", "purin", "one"]
METH, PURIN, ONE = 0, 1, 2


def test_caffeine_part_spans_are_pinned_exactly():
    spans = compute_spans(CAFFEINE, CAFFEINE_GROUPS, want_modifier=True)
    assert spans is not None
    assert CAFFEINE[slice(*spans.parts[METH])] == "1,3,7-trimethyl-"
    assert CAFFEINE[slice(*spans.parts[PURIN])] == "purine"
    assert CAFFEINE[slice(*spans.parts[ONE])] == "-2,6-dione"


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
    suffix = spans.locants[ONE]
    assert CAFFEINE[slice(*suffix["2"])] == "2"
    assert CAFFEINE[slice(*suffix["6"])] == "6"
    assert suffix["2"][0] > spans.parts[PURIN][1]


def test_caffeine_locant_spans_are_pinned_exactly():
    spans = compute_spans(CAFFEINE, CAFFEINE_GROUPS, want_modifier=True)
    assert spans.locants[METH]["1"] == (0, 1)
    assert spans.locants[METH]["3"] == (2, 3)
    assert spans.locants[METH]["7"] == (4, 5)
    assert CAFFEINE[0:1] == "1"
    assert CAFFEINE[4:5] == "7"


def test_the_same_locant_in_two_places_gets_two_different_spans():
    # Caffeine's "3" appears in "1,3,7-" (the methyls) and again in "3,7-"
    # (the hydro prefix). They mean different things and must not share a
    # span -- a flat locant map would hand the modifier the methyls' letters.
    spans = compute_spans(CAFFEINE, CAFFEINE_GROUPS, want_modifier=True)
    methyl_3 = spans.locants[METH]["3"]
    modifier_3 = spans.locants[MODIFIER_KEY]["3"]
    assert methyl_3 != modifier_3
    assert methyl_3 == (2, 3)
    assert CAFFEINE[slice(*modifier_3)] == "3"
    assert modifier_3[0] >= spans.parts[MODIFIER_KEY][0]


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
    text = CAFFEINE[slice(*spans.parts[MODIFIER_KEY])]
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


def test_ibuprofen_methyl_locant_is_its_own_not_the_parents():
    # Regression for the bracket bug: "openBracket" used to sit in _LEADING,
    # so the methyl's left-growth walked straight through "[4-(" and adopted
    # the PARENT propanoic acid's "2" (index 0) as if it belonged to the
    # methyl. The methyl's own "2" is the one inside the brackets, at index
    # 6 ("2-[4-(2-methylpropyl)phenyl]propanoic acid"). Pin the real offset,
    # not just "some span containing the text 2".
    name = "2-[4-(2-methylpropyl)phenyl]propanoic acid"
    groups = ["meth", "phenyl", "prop"]
    meth, phenyl, prop = 0, 1, 2
    spans = compute_spans(name, groups, want_modifier=False)
    assert spans is not None
    assert spans.parts[meth] == (6, 14)
    assert name[6:14] == "2-methyl"
    assert spans.locants[meth]["2"] == (6, 7)
    assert name[6:7] == "2"
    # The parent's own "2" (index 0) must NOT be what the methyl's locant
    # map points at.
    assert spans.locants[meth]["2"] != (0, 1)


def test_ibuprofen_propyl_substituent_and_propanoic_parent_get_different_spans():
    # Regression for the shared-stem bug: the propyl SUBSTITUENT
    # ("2-methylpropyl"'s chain) and the propanoic acid PARENT both strip to
    # the stem "prop". A key keyed by that text collapsed both onto the
    # substituent's occurrence, so hovering the parent underlined "propyl)"
    # -- the substituent's own letters. `group_tokens` here is what
    # `explain.py`'s `_apply_name_spans` actually builds for this name, one
    # entry per span-bearing segment, WITH the duplicate "prop" preserved, in
    # document order: methyl, propyl, phenyl, the propanoic-acid parent,
    # then its "ic acid" suffix.
    name = "2-[4-(2-methylpropyl)phenyl]propanoic acid"
    groups = ["meth", "prop", "phenyl", "prop", "ic acid"]
    meth, propyl, phenyl, parent, suffix = 0, 1, 2, 3, 4
    spans = compute_spans(name, groups, want_modifier=False)
    assert spans is not None
    assert spans.parts[propyl] == (14, 21)
    assert name[14:21] == "propyl)"
    assert spans.parts[parent] == (28, 35)
    assert name[28:35] == "propano"
    # The two "prop" positions must not share a span, and the parent's own
    # occurrence must be the LATER one in the name.
    assert spans.parts[propyl] != spans.parts[parent]
    assert spans.parts[parent][0] > spans.parts[propyl][1]
    # Sanity on the other anchors, so the whole document-order list is
    # verified, not just the two that collided.
    assert spans.parts[meth] == (6, 14)
    assert spans.parts[phenyl] == (21, 28)
    assert spans.parts[suffix] == (35, 42)


def test_tnt_part_spans_match_the_brief_reference_values_verbatim():
    # Regression for the last_end_index overlap bug: mutating
    # `last_end_index = index` (instead of `end_index`) let the methyl's
    # left-growth bound reach past the nitro run's own leading locant,
    # producing an overlap that made compute_spans discard EVERY span for
    # this name. Only caffeine was pinned before; this name's values from
    # the brief were asserted nowhere, so that mutation survived undetected.
    name = "2-methyl-1,3,5-trinitrobenzene"
    groups = ["meth", "nitro", "benzen"]
    meth, nitro, benzen = 0, 1, 2
    spans = compute_spans(name, groups, want_modifier=False)
    assert spans is not None
    assert spans.parts[meth] == (0, 9)
    assert name[0:9] == "2-methyl-"
    assert spans.parts[nitro] == (9, 23)
    assert name[9:23] == "1,3,5-trinitro"
    assert spans.parts[benzen] == (23, 30)
    assert name[23:30] == "benzene"


def test_butylcyclohexanol_part_spans_match_the_brief_reference_values_verbatim():
    name = "4-tert-butylcyclohexan-1-ol"
    groups = ["but", "hex", "ol"]
    but, hex_, ol = 0, 1, 2
    spans = compute_spans(name, groups, want_modifier=False)
    assert spans is not None
    assert spans.parts[but] == (0, 12)
    assert name[0:12] == "4-tert-butyl"
    assert spans.parts[hex_] == (12, 22)
    assert name[12:22] == "cyclohexan"
    assert spans.parts[ol] == (22, 27)
    assert name[22:27] == "-1-ol"


def test_locant_subspans_walked_cursor_does_not_confuse_a_prefix_locant():
    # No golden name has a locant token where one locant is a prefix of the
    # next (e.g. "11" then "1"), so this branch of _locant_subspans -- the
    # walked cursor documented as preventing exactly this collision -- is
    # otherwise never exercised. A naive `text.find(piece)` search (no
    # cursor) would find "1" INSIDE "11" at index 0 instead of the real
    # standalone "1" at index 3.
    token = Token(text="11,1-", category="locant", start=100, end=105)
    found = _locant_subspans(token)
    assert found["11"] == (100, 102)
    assert found["1"] == (103, 104)


# ---------------------------------------------------------------------------
# The four proofs in step 5, one test each.
#
# Every test above exercises the algorithm's HAPPY path: it proves the growth
# rules land on the right characters for names that work. None of them touched
# the fail-closed net, and that net is the entire reason spec §3.1/§8 accept a
# heuristic alignment at all -- verified by deleting each proof in turn, after
# which 23/23 tests still passed. A proof no test can kill is not a proof.
#
# Real names cannot reach these branches (that is the point: the growth rules
# are correct), so each test monkeypatches `tokenize` to hand `compute_spans`
# a token stream that violates exactly ONE proof and leaves the others
# satisfied. Each was checked by deleting its proof and confirming the test
# then fails.
# ---------------------------------------------------------------------------


def _fake_tokens(monkeypatch, tokens):
    monkeypatch.setattr("app.name_spans.tokenize", lambda name: tokens)


def test_a_span_running_past_the_end_of_the_name_is_withheld(monkeypatch):
    # The in-bounds proof. The token claims to end at 99 in a 4-character
    # name; every other proof is satisfied (name[0:99] == "meth" contains
    # "meth", one span cannot overlap, there are no locants).
    _fake_tokens(monkeypatch, [Token("meth", "substituentGroup", 0, 99)])
    assert compute_spans("meth", ["meth"], want_modifier=False) is None


def test_a_span_whose_text_lacks_its_own_group_token_is_withheld(monkeypatch):
    # The group-token containment proof. The token's TEXT is "meth" (so it
    # anchors) but its offsets point at "zzzz", which is what the user would
    # see underlined. In bounds, single span, no locants -- only this proof
    # can catch it.
    _fake_tokens(monkeypatch, [Token("meth", "substituentGroup", 0, 4)])
    assert compute_spans("zzzzmeth", ["meth"], want_modifier=False) is None


def test_two_overlapping_part_spans_withhold_the_whole_name(monkeypatch):
    # The overlap proof. Both spans are in bounds and both contain their own
    # group token, but they share characters 3-5, so one of the two is lying
    # about which letters name its atoms.
    _fake_tokens(monkeypatch, [
        Token("meth", "substituentGroup", 0, 6),
        Token("hyl", "substituentGroup", 3, 6),
    ])
    spans = compute_spans("methyl", ["meth", "hyl"], want_modifier=False)
    assert spans is None


def test_a_locant_span_that_slices_to_other_characters_is_withheld(monkeypatch):
    # The locant-text proof. The locant token says "1-" while the name has
    # "9-" at those offsets, so the locant sub-span slices to "9". The part
    # span itself is in bounds, contains "meth", does not overlap anything,
    # and the locant sub-span DOES sit inside its part -- this proof is the
    # only one left that can reject it.
    _fake_tokens(monkeypatch, [
        Token("1-", "locant", 0, 2),
        Token("meth", "substituentGroup", 2, 6),
    ])
    assert compute_spans("9-meth", ["meth"], want_modifier=False) is None


def test_a_grouped_segments_span_reports_how_many_instances_it_claims():
    # `claims` is what lets explain.py refuse a grouped segment whose span
    # cannot account for every part it owns. Pinned on the two real shapes:
    # a locant list plus a multiplier word, and a multiplier word alone.
    caffeine = compute_spans(CAFFEINE, CAFFEINE_GROUPS, want_modifier=True)
    assert CAFFEINE[slice(*caffeine.parts[METH])] == "1,3,7-trimethyl-"
    assert caffeine.claims[METH] == 3
    assert caffeine.claims[PURIN] == 1

    ddt = "1,1,1-trichloro-2,2-bis(4-chlorophenyl)ethane"
    spans = compute_spans(ddt, ["chloro", "phenyl", "eth"], want_modifier=False)
    # `1,1,1-trichloro-` claims three chlorines -- not the five that the
    # text-grouped `chloro` segment owns, which is the whole point.
    assert ddt[slice(*spans.parts[0])] == "1,1,1-trichloro-"
    assert spans.claims[0] == 3
    # `phenyl)`'s span is still just "phenyl)", but the claims WINDOW now reaches
    # left to the previous part's end, so it counts the decorating `2,2-`, `bis`
    # and `4-` that sit between the two parts. Over-counting only makes the guard
    # withhold LESS; it can never fabricate a span. The span offsets are unchanged.
    assert ddt[slice(*spans.parts[1])] == "phenyl)"
    assert spans.claims[1] == 3

    name = "diethyl carbonate"
    spans = compute_spans(name, ["eth", "carbon"], want_modifier=False)
    assert name[slice(*spans.parts[0])] == "diethyl"
    assert spans.claims[0] == 2


def test_never_returns_a_span_that_does_not_contain_its_group_token():
    # The safety property, stated directly: whatever names DO produce spans,
    # each span must literally contain the token it was anchored on.
    for name in GOLDEN_NAMES:
        for groups in (["meth"], ["benzen"], ["prop"], ["eth"]):
            spans = compute_spans(name, groups, want_modifier=False)
            if spans is None:
                continue
            for position, (start, end) in spans.parts.items():
                assert groups[position] in name[start:end], (
                    f"{name}: span for {groups[position]!r} is {name[start:end]!r}"
                )


def test_a_locant_list_outside_the_span_still_counts_toward_claims():
    # 1,1,2,2-tetrachloroethane's locant list sits BEFORE the chloro span,
    # because the two-token multiplier between them is not absorbed. The
    # count must still see its four positions, or the guard withholds a name
    # whose span is perfectly correct.
    spans = compute_spans(
        "1,1,2,2-tetrachloroethane", ["chloro", "eth"], want_modifier=False
    )
    assert spans is not None
    assert spans.claims[0] == 4, f"chloro claims {spans.claims[0]}, need 4"


def test_widening_the_window_does_not_inflate_a_later_part():
    # The window must start at the PREVIOUS part's end, not at 0 -- otherwise
    # every part inherits every earlier locant and the guard stops guarding.
    name = "2-methyl-1,3,5-trinitrobenzene"
    spans = compute_spans(name, ["meth", "nitro", "benzen"], want_modifier=False)
    assert spans is not None
    assert spans.claims[0] == 1, "methyl has one locant, must claim 1"
    assert spans.claims[1] == 3, "nitro has three locants, must claim 3"
