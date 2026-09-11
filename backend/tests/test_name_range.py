from app.explain import explain_name
from app.opsin_tokenizer import tokenize
from tests.conftest import CAFFEINE, GOLDEN_NAMES


def _locant_text_present(name: str, start: int, end: int, locant: str) -> bool:
    """Is `locant`'s own text really sitting somewhere inside `name[start:end]`?

    An independent check for the invariant test below -- it re-tokenizes
    `name` from scratch via the real OPSIN tokenizer (`opsin_tokenizer.
    tokenize`, not `explain.py`'s own collector) and asks, per RAW TOKEN
    whose offsets sit fully inside the window, whether `locant` is one of
    that token's own comma-separated pieces, less a trailing "-" (a locant
    token's own closing hyphen) and less a trailing "H" (an indicated-
    hydrogen token's own element marker, glued directly onto its locant:
    "1H-" is the locant "1" plus that marker, not two characters of one
    locant; "9bH-" is the locant "9b" the same way).

    A first version of this oracle used a hand-rolled word-boundary regex
    over the raw window text instead of real tokens, and got exactly this
    case wrong: it treated a glued "H" as an ordinary word character, so
    its negative lookahead refused to recognise "1" as present inside
    "1H-" at all -- the one shape this task's whole fix exists for. That
    silently left the invariant with no protection for anything but
    caffeine (pinned separately by
    `test_caffeines_indicated_hydrogen_locant_is_hoverable`): forcing
    `1H-indole`'s or `4H-pyran`'s indicated-hydrogen child back to `None`
    passed the old regex clean, because it could not see the "1" or "4"
    was ever there to miss. Walking real tokens and comparing whole
    pieces sidesteps boundary-guessing entirely: a piece either equals
    the locant (a plain `locant`-category token) or equals it plus one
    trailing "H" (a `bigCapitalH`-category token), and nothing else can
    match by accident.
    """
    tokens = tokenize(name)
    if not tokens:
        return False
    for token in tokens:
        if token.start < start or token.end > end:
            continue
        for piece in token.text.rstrip("-").split(","):
            if not piece:
                continue
            if piece == locant or (piece.endswith("H") and piece[:-1] == locant):
                return True
    return False


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
    # Filtered to kind == "substituent": the methyl segment's children now
    # also include TOKEN siblings ("tri", the "1,3,7-" locant token itself),
    # which are a separate concern from the per-locant children pinned here.
    got = {
        c["locant"]: name[slice(*c["name_range"])]
        for c in methyl["children"] if c["kind"] == "substituent"
    }
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
    # Filtered to kind == "suffix" for the same reason as the methyl case
    # above: the suffix segment's children now also include a TOKEN sibling
    # ("di", the multiplier word).
    got = {
        c["locant"]: name[slice(*c["name_range"])]
        for c in suffix["children"] if c["kind"] == "suffix"
    }
    assert got == {"2": "2", "6": "6"}


def test_ddt_withholds_every_span_because_one_chloro_span_cannot_name_five():
    # The grouped-substituent defect, pinned by concrete offsets. Substituent
    # parts are grouped by TEXT, so all five of DDT's chlorines land in one
    # `chloro` segment, while the span is anchored on the FIRST occurrence
    # only: `1,1,1-trichloro-` == name[0:16], whose three locants name three
    # chlorines. The other two are named by the `4-chloro` at name[24:32] --
    # text that would be covered by NO span and so render inert, while the
    # three characters `1,1,1` glowed atoms belonging to a different
    # numbering scope. All four of compute_spans' proofs pass on that answer,
    # so the whole name must fall back instead (spec §4 all-or-nothing).
    name = "1,1,1-trichloro-2,2-bis(4-chlorophenyl)ethane"
    result = explain_name(name)
    assert result["error"] is None
    assert name[0:16] == "1,1,1-trichloro-"
    assert name[24:32] == "4-chloro"
    chloro = next(s for s in result["segments"] if s["label"] == "chloro")
    assert len(chloro["atom_indices"]) == 5, chloro["atom_indices"]
    # Not one segment, and not one child, may hold a span.
    assert result["segments"], "expected a real decomposition, not an empty one"
    assert [s["name_range"] for s in result["segments"]] == [
        None for _ in result["segments"]
    ]
    for segment in result["segments"]:
        for child in segment["children"]:
            assert child["name_range"] is None, (segment["label"], child["locant"])


def test_caffeine_still_has_all_four_spans_after_the_ddt_withholding_rule():
    # The other side of the rule: caffeine's three methyls are named by ONE
    # token (`1,3,7-trimethyl`, whose own text claims three), so nothing is
    # withheld and every pinned offset stands.
    result = explain_name(CAFFEINE)
    name = result["name"]
    assert len(result["segments"]) == 4
    assert all(s["name_range"] is not None for s in result["segments"])
    got = {s["kind"]: name[slice(*s["name_range"])] for s in result["segments"]}
    assert got == {
        "substituent": "1,3,7-trimethyl-",
        "modifier": "3,7-dihydro-1H-",
        "parent": "purine",
        "suffix": "-2,6-dione",
    }


def test_one_token_naming_several_substituents_keeps_its_span():
    # Legitimate multiplied substituents must NOT regress. Three shapes:
    # a locant list plus a multiplier word (trinitro, dimethyl), and a
    # multiplier word with no locants at all (diethyl).
    for name, label, expected in (
        ("2-methyl-1,3,5-trinitrobenzene", "nitro", "1,3,5-trinitro"),
        ("1,2-dimethylbenzene", "methyl", "1,2-dimethyl"),
        ("2,2-dimethylpropane", "methyl", "2,2-dimethyl"),
        ("diethyl carbonate", "ethyl", "diethyl"),
    ):
        result = explain_name(name)
        assert result["error"] is None, name
        segment = next(s for s in result["segments"] if s["label"] == label)
        assert segment["name_range"] is not None, name
        assert name[slice(*segment["name_range"])] == expected


def test_a_second_written_occurrence_of_a_substituent_forces_the_fallback():
    # Every one of these writes the same substituent text twice, so the one
    # span it gets would own atoms the other occurrence names. Measured live
    # before the fix: p-cymene's `methyl` span was name[0:9] == '1-methyl-'
    # while owning atoms [0, 9], and atom 9 is the isopropyl's methyl carbon,
    # named by the `1-methyl` at name[12:20].
    for name in (
        "1-methyl-4-(1-methylethyl)benzene",
        "methyl 2-methylpropanoate",
        "2-chloro-4-(4-chlorophenyl)phenol",
    ):
        result = explain_name(name)
        assert result["error"] is None, name
        assert result["segments"], name
        assert all(s["name_range"] is None for s in result["segments"]), name
    assert "1-methyl-4-(1-methylethyl)benzene"[12:20] == "1-methyl"


def test_a_repeated_unlocanted_hydro_substituent_still_forces_the_fallback():
    # Same family as test_a_second_written_occurrence_of_a_substituent_
    # forces_the_fallback above, but the repeated substituent is itself an
    # unlocanted hydro ring ("tetrahydrofuran-2-yl"). Measured live before
    # the claims-window fence: the "furanyl" segment's own claims window
    # swept in the leaked "tetr" from its OWN preceding, unlocanted
    # "tetrahydro" run (no locant on that hydro token, so no MODIFIER_KEY
    # part bounds it), inflating claims from 1 to 4 -- enough to satisfy
    # owned_by(2) <= claims(4) and let a span through for the FIRST
    # "tetrahydrofuran" occurrence's text while the segment's atom_indices
    # covered BOTH ring occurrences. The fence must restore the correct
    # all-or-nothing fallback here exactly as it does for phenyl above.
    name = "1-(tetrahydrofuran-2-yl)-2-(tetrahydrofuran-2-yl)ethane"
    assert name[13:18] == "furan"
    result = explain_name(name)
    assert result["error"] is None
    furanyl = next(s for s in result["segments"] if s["label"] == "furanyl")
    assert len(furanyl["atom_indices"]) == 10, furanyl["atom_indices"]
    assert result["segments"], "expected a real decomposition, not an empty one"
    assert [s["name_range"] for s in result["segments"]] == [
        None for _ in result["segments"]
    ]


def test_the_repeated_locant_3_points_at_different_letters_per_part():
    # "3" appears in "1,3,7-" and again in "3,7-". The methyl child and the
    # modifier child must underline DIFFERENT characters.
    result = explain_name(CAFFEINE)
    by_kind = {s["kind"]: s for s in result["segments"]}
    methyl_3 = next(c for c in by_kind["substituent"]["children"] if c["locant"] == "3")
    modifier_3 = next(c for c in by_kind["modifier"]["children"] if c["locant"] == "3")
    assert methyl_3["name_range"] != modifier_3["name_range"]


def test_a_two_token_multiplier_still_keeps_its_span():
    # "tetra" tokenizes as tetrOrHigher ("tetr") + "a" -- TWO tokens -- and
    # tetrOrHigher was not in _LEADING, so it was never absorbed into a
    # run's own fillers. A first, narrower claims computation (counting
    # only a run's own `fillers`) silently dropped this substituent's claim
    # from 4 to 1, wrongly withholding this name end-to-end even though it
    # was CLEAN in production before this task. `explain.py`'s
    # `_compute_claims` must window the count back to the previous run's
    # end (matching `compute_spans` step 4b) to recover it.
    #
    # The asserted span below changed FROM "methyl" TO "tetramethyl" in a
    # later task on this same branch (Task 5), which added `tetrOrHigher`
    # and `a` to `_LEADING` itself -- not just to the claims window. Before
    # that, this substituent's span stopped short of its own multiplier,
    # inconsistent with every ONE-token multiplier ("tri" in caffeine's
    # "1,3,7-trimethyl", TNT's "1,3,5-trinitro"), which `_LEADING` already
    # absorbed. `name_tokens.py`'s own documented rule for `_LEADING` is
    # that a multiplier word decorates the run it multiplies and belongs to
    # ITS span -- so "tetramethyl", not "methyl", is what that rule already
    # said for every other multiplier and had simply never been extended to
    # the two-token spelling. Confirmed by reverting the `_LEADING` change
    # alone: this test passes against "methyl" on the old set and against
    # "tetramethyl" on the new one, so the assertion below is pinned to
    # real, current behaviour, not merely restated to match it.
    name = "tetramethylammonium chloride"
    result = explain_name(name)
    assert result["error"] is None
    assert result["segments"], "expected a real decomposition, not an empty one"
    assert all(s["name_range"] is not None for s in result["segments"]), (
        result["segments"]
    )
    methyl = next(s for s in result["segments"] if s["label"] == "methyl")
    assert name[slice(*methyl["name_range"])] == "tetramethyl"


def test_a_coincidental_stem_collision_withholds_everything():
    # "methoxy" and "methyl" both strip to the bare stem "meth" -- and are
    # adjacent in document order, with a "6,7-" locant ahead of them that
    # satisfies `assign_runs`' clone-group check by coincidence (it exists
    # for a caller that hands it one entry per RAW OPSIN part; fed the
    # per-SEGMENT entries `_build_segments` already merges, an adjacent
    # shared-stem pair here can only ever be a coincidence, never a
    # legitimate multiplication). Without the caller-side guard,
    # `assign_runs` folds both into ONE run and the "methyl" segment gets
    # handed the "methoxy" segment's span -- a wrong letters-to-atoms claim,
    # not merely a missing one. Every top-level span must be withheld.
    name = "6,7-dimethoxy-1-methylisoquinoline"
    result = explain_name(name)
    assert result["error"] is None
    assert result["segments"], "expected a real decomposition, not an empty one"
    assert all(s["name_range"] is None for s in result["segments"]), (
        result["segments"]
    )


def test_the_other_stem_collision_shape_also_withholds_everything():
    # The other measured shape of the same defect: a SUBSTITUENT and the
    # PARENT (not two substituents) share a stem -- "ethyl" and "ethamine"
    # (root text, after its "amine" suffix is stripped) both reduce to
    # "eth". Same guard, different segment kinds colliding.
    name = "N,N-diethylethanamine"
    result = explain_name(name)
    assert result["error"] is None
    assert result["segments"], "expected a real decomposition, not an empty one"
    assert all(s["name_range"] is None for s in result["segments"]), (
        result["segments"]
    )


def test_caffeines_indicated_hydrogen_locant_is_hoverable():
    """The hole in the reference example. `3` and `7` of the hydro run were
    live and the `1` of `1H-` was dead, so one locant of the best-working
    name in the product could not be hovered. Caffeine scored 11 of 12.
    """
    from app.explain import explain_name
    from tests.fixtures.explain_corpus import CAFFEINE

    payload = explain_name(CAFFEINE)
    modifier = next(
        s for s in payload["segments"] if s["kind"] == "modifier"
    )
    by_locant = {c["locant"]: c["name_range"] for c in modifier["children"]}
    assert by_locant["3"] is not None
    assert by_locant["7"] is not None
    assert by_locant["1"] is not None, "the 1 of 1H- is still dead"


def test_every_locant_child_of_a_spanned_segment_has_a_span():
    """Stated as an invariant over the curated corpus, so a future change
    cannot re-open the hole this task closed somewhere else.

    Not a blanket `holes == []`: some locants are honestly unwritable.
    IUPAC omits a suffix locant entirely when the parent's own numbering
    leaves only one possible position for it -- `ethanol`'s suffix
    genuinely carries locant "1" (there is only one carbon it could be),
    but the string "ethanol" contains no "1" anywhere for a span to point
    at. The child keeps its explanation line ("attached at position 1"
    is still useful to read even with nothing to hover); only its
    `name_range` stays `None`, which is the honest answer, not a defect --
    the same as this suite's own `test_ddt_withholds_...` and the spec's
    "never guess" rule.

    So a missing span is only counted as a HOLE -- worth failing the test
    over -- when the locant's own text is actually sitting inside its
    segment's OWN already-proven span and got missed anyway. That check
    (`_locant_text_present` above) is deliberately independent of
    `explain.py`'s own collector (`_locant_subspans`/`_bigcapitalh_
    subspans`) -- it re-tokenizes from scratch and compares whole raw
    token pieces, not offsets -- so this stays a real invariant rather
    than the implementation grading its own homework.
    """
    from app.explain import explain_name
    from tests.fixtures.explain_corpus import CURATED

    holes = []
    for _axis, name in CURATED:
        payload = explain_name(name)
        if payload["error"] is not None:
            continue
        for segment in payload["segments"]:
            if segment["name_range"] is None:
                continue
            start, end = segment["name_range"]
            for child in segment["children"]:
                locant = child["locant"]
                if not locant or child["name_range"] is not None:
                    continue
                if _locant_text_present(name, start, end, locant):
                    holes.append((name, segment["label"], locant))
    assert holes == [], holes


def _hover_owner_by_offset(payload: dict) -> dict:
    """Python port of the frontend's OWN hover-resolution algorithm --
    `frontend/src/lib/nameTargets.js`'s `nameTargets()` (build one target
    per segment/child with a `name_range`, at depth 0/1) composed with
    `sliceName()`'s ownership pass (first-claim-wins over the targets in
    `nameTargets()`'s own sort order: depth DESCENDING, then `range[0]`
    ASCENDING, ties broken by list order because both JS's `Array.sort`
    and Python's `list.sort` are stable).

    This exists because the JSON payload alone cannot show a shadowing
    regression: a same-depth sibling with a WIDER range that happens to
    start no later can still win a character away from a narrower,
    more precise sibling, even though both children are present and
    individually correct in isolation. Verified live before the fix this
    test guards: a `locant`-category token child ("1,3,7-", [0,6)) started
    at the SAME offset as caffeine's own precise "1" locant child ([0,1))
    but, being wider, also swallowed "3" ([2,3)) and "7" ([4,5)) -- neither
    of which starts as early as the token, so the token's own EARLIER (or
    tied) `range[0]` let it win the sort position and claim their
    characters first, regardless of the token being built and appended
    to the children list after them.

    Returns `{char_offset: (segment, child_or_None)}` for every character
    some target's range covers.
    """
    targets = []
    for s_index, segment in enumerate(payload["segments"]):
        if segment["name_range"] is not None:
            targets.append((0, segment["name_range"][0], s_index, segment, None))
        for c_index, child in enumerate(segment["children"]):
            if child["name_range"] is not None:
                targets.append((1, child["name_range"][0], (s_index, c_index), segment, child))

    # Stable sort: depth DESCENDING (children win over their own parent),
    # then range[0] ASCENDING -- exactly nameTargets.js's own comparator.
    # Ties (equal depth AND equal range[0]) keep their ORIGINAL list order,
    # which is why insertion order (locant children built before token
    # children are appended) can still matter for a tie specifically.
    targets.sort(key=lambda t: (-t[0], t[1]))

    owner = {}
    for _depth, _start, _path, segment, child in targets:
        name_range = child["name_range"] if child is not None else segment["name_range"]
        for offset in range(name_range[0], name_range[1]):
            if offset not in owner:
                owner[offset] = (segment, child)
    return owner


def test_precise_locant_children_are_not_shadowed_by_a_coarser_token_sibling():
    """Fix-round-1 regression guard. A `"locant"`-category token child used
    to exist alongside the precise per-position locant children Task 5
    built, and -- proven by replaying the REAL frontend ownership algorithm
    above, not by inspecting the JSON -- silently won the hover for "3" and
    "7" away from their own precise children, because the coarse token's
    range started no later than theirs. The JSON alone looked fine (both
    children were present, both individually correct); only replaying
    `nameTargets`/`sliceName`'s own resolution rule exposes the shadowing.
    `describe_token` no longer has a `"locant"` entry, so this class of
    token child cannot be produced at all any more -- this test is the
    proof, not just the removal.
    """
    result = explain_name(CAFFEINE)
    name = result["name"]
    owner = _hover_owner_by_offset(result)

    methyl = next(s for s in result["segments"] if s["kind"] == "substituent")
    by_locant = {
        c["locant"]: c for c in methyl["children"] if c["kind"] == "substituent"
    }
    assert set(by_locant) == {"1", "3", "7"}

    for locant in ("1", "3", "7"):
        child = by_locant[locant]
        start, end = child["name_range"]
        assert name[start:end] == locant, (locant, name[start:end])
        for offset in range(start, end):
            owning_segment, owning_child = owner[offset]
            assert owning_child is child, (
                f"caffeine offset {offset} ({name[offset]!r}, locant "
                f"{locant!r}) is owned by "
                f"{(owning_child or owning_segment)['label']!r} "
                f"({(owning_child or owning_segment)['kind']}) instead of "
                f"its own precise locant child"
            )


# ---------------------------------------------------------------------------
# Moved from test_name_spans.py (Task 7). These test explain_name's own
# production behaviour -- name_tokens.assign_runs and _apply_name_spans --
# not the deleted compute_spans/SpanSet/MODIFIER_KEY, so they belong here
# rather than dying with that module.
#
# `_apply_name_spans` sources its top-level spans from
# `name_tokens.assign_runs`, not from the old anchor scan (`compute_spans`,
# which tested equality against a SINGLE raw token and withheld every
# fusion-bracket and ring-assembly name in the census -- 80 names --
# because their labels are several tokens wide).
# ---------------------------------------------------------------------------


def test_a_fusion_parent_gets_a_span():
    """All 40 fusion-bracket names in the census withheld every span. The
    label is three raw tokens wide and the anchor scan tested equality
    against one.
    """
    payload = explain_name("benzo[a]pyrene")
    assert payload["error"] is None
    parents = [s for s in payload["segments"] if s["kind"] == "parent"]
    assert parents, payload["segments"]
    assert parents[0]["name_range"] is not None


def test_a_primed_ring_assembly_gets_a_span():
    """All 40 ring-assembly names withheld. 'biphenyl' is bi|phenyl in the
    stream.
    """
    payload = explain_name("1,1'-biphenyl")
    assert payload["error"] is None
    assert any(s["name_range"] is not None for s in payload["segments"])


def test_caffeine_still_spans_every_top_level_part():
    """The reference example. Its four top-level parts covered [0,47] before
    this change and must still cover it after.

    `CAFFEINE` here is the module's own import from `tests.conftest`; the
    original (test_name_spans.py) instead imported it from
    `tests.fixtures.explain_corpus`, but the two are the same literal
    string, so this is the same molecule under the name this module
    already uses everywhere else.
    """
    payload = explain_name(CAFFEINE)
    ranges = [s["name_range"] for s in payload["segments"]]
    assert all(r is not None for r in ranges), ranges
    assert min(r[0] for r in ranges) == 0
    assert max(r[1] for r in ranges) == len(CAFFEINE)


def test_a_duplicated_heteroatom_label_still_withholds_everything():
    """The named residue. OPSIN duplicates the az token, so the label is not
    any ordered concatenation of the stream. Withhold -- never guess.
    """
    payload = explain_name("[1,2,4]triazolo[4,3-a]pyridine")
    assert payload["error"] is None
    assert all(s["name_range"] is None for s in payload["segments"])


def test_a_capital_d_sugar_tokenizes():
    """OPSIN's ParseRules matches dlStereochemistry case-insensitively and
    hands back a lowercased `d` where the name wrote `D`. The exact
    reconstruction guard then rejected OPSIN's own answer and returned None,
    so compute_spans (and everything downstream of `tokenize`) died on its
    second line for every D-/L- sugar and amino acid.
    """
    tokens = tokenize("alpha-D-glucopyranose")
    assert tokens is not None


def test_the_reconstructed_token_keeps_the_names_own_casing():
    """The span text is what the page renders, so a lowercased `d` would
    make the highlighted letters differ from the letters on screen. Each
    token's `.text` must come from the ORIGINAL name, not OPSIN's
    case-folded copy of it -- so this join must match `name` EXACTLY,
    case included, not just case-insensitively.
    """
    name = "alpha-D-glucopyranose"
    tokens = tokenize(name)
    assert tokens is not None
    assert "".join(t.text for t in tokens) == name


def test_a_lowercased_multiword_token_also_keeps_its_own_casing():
    """The multi-word fallback path (methyl-acetate-style ester names) has
    its own, separate reconstruction guard from the single-word path --
    `methyl beta-D-galactopyranoside` only reaches OPSIN's lowercased `d`
    by going through it, since the whole string never parses as one call.
    Both guards had to be fixed, not just the one the single-word sugar
    test above already exercises.

    Unlike the single-word case, `"".join(t.text for t in tokens) == name`
    does NOT hold here -- no token owns the space between "methyl" and
    "beta-D-galactopyranoside" (the multi-word path advances `pos` over it
    without emitting a Token for it), so the join skips that character even
    on already-correct, pre-existing multi-word names like "methyl
    acetate". The invariant the renderer actually depends on, and the one
    that must hold on both paths, is that every individual token's `.text`
    is exactly the original name's own slice at that token's own offsets --
    checked here directly against `name`, not against OPSIN's returned
    value.
    """
    name = "methyl beta-D-galactopyranoside"
    tokens = tokenize(name)
    assert tokens is not None
    assert all(t.text == name[t.start:t.end] for t in tokens)
    # And the case survived: OPSIN's own answer for this token is the
    # lowercased "d", but the slice taken from `name` is the "D" it wrote.
    d_tokens = [t for t in tokens if t.category == "dlStereochemistry"]
    assert len(d_tokens) == 1
    assert d_tokens[0].text == "D"


def test_a_genuinely_partial_single_word_parse_still_withholds():
    """The case-fold relaxation must not loosen the guard into accepting a
    PARTIAL parse -- only tolerate case. "phenylacetatex" has no space, so
    it can only ever go through the single-word path, and OPSIN parses only
    "phenylacetate" out of it (confirmed directly against `_tokenize_raw`:
    it returns the tokens for "phenylacetate" and stops, leaving the
    trailing "x" unconsumed). That mismatch is a real length/content
    difference, not a casing difference, so it must still return None both
    before and after the case-fold fix.
    """
    tokens = tokenize("phenylacetatex")
    assert tokens is None
