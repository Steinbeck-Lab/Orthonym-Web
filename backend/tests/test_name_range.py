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
    # tetrOrHigher is not in _LEADING, so it is never absorbed into a run's
    # own fillers. A first, narrower claims computation (counting only a
    # run's own `fillers`) silently dropped this substituent's claim from 4
    # to 1, wrongly withholding this name end-to-end even though it was
    # CLEAN in production before this task. `explain.py`'s `_compute_claims`
    # must window the count back to the previous run's end (matching
    # `compute_spans` step 4b) to recover it.
    name = "tetramethylammonium chloride"
    result = explain_name(name)
    assert result["error"] is None
    assert result["segments"], "expected a real decomposition, not an empty one"
    assert all(s["name_range"] is not None for s in result["segments"]), (
        result["segments"]
    )
    methyl = next(s for s in result["segments"] if s["label"] == "methyl")
    assert name[slice(*methyl["name_range"])] == "methyl"


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
