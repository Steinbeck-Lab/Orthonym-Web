"""opsin_trace: one tagged OPSIN run -> atoms, written tokens, owners, parts, stereo."""

import pytest
from celery.exceptions import SoftTimeLimitExceeded
from rdkit import Chem

from app import opsin_trace
from app.opsin_trace import Trace, TraceFailure, trace, trace_from_dict, trace_to_dict
from tests.conftest import CAFFEINE
from tests.fixtures.explain_corpus import CURATED, FULL

GLUE_TEXT = set("-,'()[]{} ")


def _canon(smiles):
    return Chem.MolToSmiles(Chem.MolFromSmiles(smiles))


def test_ethanol_tokens_parts_and_atoms():
    t = trace("ethanol")
    assert isinstance(t, Trace)
    assert [(tok.kind, t.text[tok.span[0]:tok.span[1]]) for tok in t.tokens] == [
        ("group", "eth"), ("unsaturator", "an"), ("suffix", "ol"),
    ]
    assert len(t.parts) == 1 and t.parts[0].kind == "root"
    assert sorted(t.parts[0].atoms) == [0, 1, 2]
    assert all(tok.owner == t.parts[0].span for tok in t.tokens)
    assert _canon(t.smiles) == "CCO"


def test_caffeine_methyl_copies_share_one_key():
    t = trace(CAFFEINE)
    methyls = [p for p in t.parts if p.kind == "substituent"]
    assert len(methyls) == 3 and len({p.span for p in methyls}) == 1
    assert sorted(p.locant for p in methyls) == ["1", "3", "7"]
    assert all(len(p.atoms) == 1 for p in methyls)
    assert sorted(a for p in t.parts for a in p.atoms) == list(range(14))


def test_opsin_moves_the_hydro_prefix_into_the_ring():
    # ComponentProcessor detaches "3,7-dihydro" and puts it in the purine root.
    t = trace(CAFFEINE)
    (root,) = [p for p in t.parts if p.kind == "root"]
    (hydro,) = [tok for tok in t.tokens if tok.kind == "hydro"]
    assert hydro.owner == root.span


def test_a_bracket_locant_is_used_up_not_owned_by_the_first_substituent():
    # At parse time "2-[4-(" sits inside the methyl substituent; OPSIN turns
    # those locants into bracket attributes. They must not claim an owner.
    t = trace("2-[4-(2-methylpropyl)phenyl]propanoic acid")
    lead = [tok for tok in t.tokens if tok.kind == "locant" and tok.span[0] < 6]
    assert [t.text[a:b] for a, b in (tok.span for tok in lead)] == ["2-", "4-"]
    assert all(tok.owner is None for tok in lead)


@pytest.mark.parametrize("axis,name", CURATED + FULL)
def test_written_tokens_cover_the_name_in_order(axis, name):
    t = trace(name)
    if isinstance(t, TraceFailure):
        return
    spans = [tok.span for tok in t.tokens]
    assert all(a[1] <= b[0] for a, b in zip(spans, spans[1:])), name       # strictly in order
    covered = {i for a, b in spans for i in range(a, b)}
    run = 0
    for i, ch in enumerate(t.text):
        if i in covered or ch in GLUE_TEXT:
            run = 0
            continue
        run += 1
        assert run <= 3, (name, t.text[i - run + 1:i + 1])                # only elided letters / "ose"


def test_a_part_keeps_the_text_of_tokens_opsin_deletes():
    t = trace("alpha-D-glucopyranose")
    (root,) = [p for p in t.parts if p.kind == "root"]
    assert len(root.atoms) == 12
    assert {tok.kind for tok in t.tokens if tok.owner is None} >= {"locant", "carbohydrateRingSize"}


def test_ester_root_copies_share_one_key():
    t = trace("propane-1,2,3-triyl trioctadecanoate")
    roots = [p for p in t.parts if p.kind == "root"]
    assert len(roots) == 3 and len({p.span for p in roots}) == 1
    assert all(len(p.atoms) == 20 for p in roots)


def test_not_a_name_is_unreadable():
    assert trace("zzz not a name") == TraceFailure("unreadable")


def test_missing_reflection_is_unavailable(monkeypatch):
    monkeypatch.setattr(opsin_trace, "_get_handles", lambda: None)
    assert trace("ethanol") == TraceFailure("unavailable")
    assert opsin_trace.self_check() is False


def test_a_chemistry_mismatch_is_rejected(monkeypatch):
    monkeypatch.setattr(opsin_trace, "_same_molecule", lambda h, name, smiles: False)
    assert trace("ethanol") == TraceFailure("mismatch")


def test_trace_round_trips_through_json():
    t = trace(CAFFEINE)
    assert trace_from_dict(trace_to_dict(t)) == t


@pytest.mark.parametrize("name", [
    "acetic acid, ethyl ester",
    "benzoic acid, 4-amino-, ethyl ester",
    "Ethanol, 2-amino-",
])
def test_a_name_opsin_reorders_is_unplaced(name):
    # OPSIN reads CAS index names in uninverted form, so the written tokens no
    # longer run in parse order; refusing beats lighting the wrong atoms.
    assert trace(name) == TraceFailure("unplaced")


def test_a_soft_time_limit_is_not_swallowed(monkeypatch):
    def boom(h, parse_el, text):
        raise SoftTimeLimitExceeded()

    monkeypatch.setattr(opsin_trace, "_trace_one", boom)
    with pytest.raises(SoftTimeLimitExceeded):
        trace("ethanol")


def test_the_corpus_is_not_vacuously_refused():
    # The per-name test above returns early on a failure; this floor stops a
    # change that refuses everything from passing it.
    traced = sum(isinstance(trace(n), Trace) for _, n in CURATED + FULL)
    assert traced >= 550
