"""Explain coverage census (spec §8.4). On demand -- too slow for the gate.

    cd backend && PYTHONPATH="$(pwd)" REDIS_URL=redis://localhost:6379/11 \
      .venv/bin/python scripts/explain_census.py [--chembl tests/fixtures/explain_chembl_10k.tsv]

Outcomes, measured on the trace and the node list (a name may carry several):
  CLEAN               nothing below
  UNREADABLE          OPSIN cannot read the name (reported, not a failure)
  UNAVAILABLE         reflection disabled (a failure: the census ran blind)
  MISMATCH            traced molecule != OPSIN's public parse
  UNPLACED            OPSIN read the name in a reordered form (a CAS index name):
                      its parts cannot be tied to the text (a failure; not the
                      same as PART_UNPLACED, which is a node without a span)
  NODE_ERROR          build_nodes raised
  PART_UNPLACED       a substituent/parent/suffix node has no span
  ATOM_GAP            part nodes do not own every heavy atom
  ATOM_OVERLAP        an atom is owned twice
  BAD_SPAN            a span outside the name or empty
  CROSSING            two spans overlap without nesting
  LABEL_EDGE          a part label starts/ends with glue or leaves a bracket open
  ORPHAN_TOKEN        a written token no part and no bracket owns
  HYDRO_WRONG         a hydro / indicated-hydrogen locant lights nothing, or an
                      atom not carrying that locant
  STEREO_NO_PARENT    a stereo node with no part
  STEREO_WRONG_ATOM   a stereo mark with a locant lights an atom without that
                      locant, an atom that is not a stereocentre (R/S,
                      alpha/beta) or not on a stereo double bond (E/Z), or
                      more than one atom
  LOCANT_UNLIT        a locant node lights nothing (a sugar's alpha/beta, whose
                      anomeric carbon the structure cannot prove, lights nothing
                      by design and is not counted)
  LIT_ATOM_FOREIGN    a locant node lights an atom it has no claim on: not in its
                      own part, not a copy OPSIN placed at that locant, and not
                      the atom carrying that locant that the part's substituent
                      chain is bonded to (app.explain_tree.foreign_lights)
Every outcome except CLEAN and UNREADABLE fails the run (exit 1).
"""

import argparse
import collections
import os
import re
import sys

PART_KINDS = ("substituent", "parent", "suffix")
_STEREO_MARK = re.compile(r"^(\d+[a-z]?'*)([RSrs]\*?|[EZ]|alpha|beta)$")
PASSING = {"CLEAN", "UNREADABLE"}


def _spiro_primes(trace, node, loc: str) -> int:
    """How many primes OPSIN puts on the atom a locant names. In
    spiro[A-x,y'-B] every locant written after the spiro locants of THAT spiro
    system is a position of a later component, and OPSIN numbers those atoms
    1', 2', ... (a second spiro locant makes the third component ''). A name
    may hold several spiro systems; only the one the node is written in counts.
    The gate still demands an EXACT locant: an atom carrying the bare number in a
    later component is wrong."""
    if loc.endswith("'") or not node["span"]:
        return 0
    start = node["span"][0]
    heads = [t for t in trace.tokens if t.kind == "polyCyclicSpiro" and t.span[1] <= start]
    if not heads:
        return 0
    head = heads[-1]
    return sum(1 for t in trace.tokens if t.kind == "spiroLocant" and head.span[1] <= t.span[0]
               and t.span[1] <= start)


def classify(trace, nodes, owners) -> list[str]:
    """`trace` is a Trace, `nodes` build_nodes(trace), `owners`
    assign_owners(trace.tokens)."""
    from app.explain_tree import _stereo_atoms, foreign_lights
    out = []
    parts = [n for n in nodes if n["kind"] in PART_KINDS]
    if any(n["span"] is None for n in parts):
        out.append("PART_UNPLACED")
    owned = [a for n in parts for a in n["owns"]]
    if set(owned) != set(range(len(trace.atoms))):
        out.append("ATOM_GAP")
    if len(owned) != len(set(owned)):
        out.append("ATOM_OVERLAP")
    spans = [tuple(n["span"]) for n in nodes if n["span"]]
    if any(not (0 <= a < b <= len(trace.text)) for a, b in spans):
        out.append("BAD_SPAN")
    if any(a[0] < b[0] < a[1] < b[1] for a in spans for b in spans):
        out.append("CROSSING")
    for n in parts:
        label = n["label"]
        if n["span"] and (not label or label[0] in "-,')]}" or label[-1] in "-,([{"
                          or any(label.count(o) != label.count(c) for o, c in ("()", "[]", "{}"))):
            out.append("LABEL_EDGE")
            break
    if any(owner is None for owner in owners.values()):
        out.append("ORPHAN_TOKEN")
    for n in nodes:
        if n["kind"] == "indicated_h" or (n["kind"] == "locant" and "hydrogen" in n["line"]):
            loc = n["label"][:-1] if n["kind"] == "indicated_h" else n["label"]
            loc = loc + "'" * _spiro_primes(trace, n, loc)
            if not n["lights"] or any(loc not in trace.atoms[a].locants for a in n["lights"]):
                out.append("HYDRO_WRONG")
                break
    for n in nodes:
        if n["kind"] != "stereo":
            continue
        if n["parent"] is None:
            out.append("STEREO_NO_PARENT")
            break
    centres, double = _stereo_atoms(trace.smiles)
    for n in nodes:
        m = _STEREO_MARK.match(n["label"]) if n["kind"] == "stereo" else None
        if not m or not n["lights"]:
            continue       # a mark that names no single atom lights nothing, by design
        pool = double if m.group(2) in ("E", "Z") else centres
        if len(n["lights"]) != 1 or any(
                m.group(1) not in trace.atoms[a].locants or a not in pool for a in n["lights"]):
            out.append("STEREO_WRONG_ATOM")
            break
    for n in nodes:
        if n["kind"] == "stereo" and re.match(r"^([RSrs]\*?|[EZ])$", n["label"]) and n["lights"]:
            pool = double if n["label"] in ("E", "Z") else centres
            if len(n["lights"]) != 1 or n["lights"][0] not in pool:
                out.append("STEREO_WRONG_ATOM")
                break
    if any(n["kind"] == "locant" and not n["lights"] and n["label"].lower() not in ("alpha", "beta")
           for n in nodes):
        out.append("LOCANT_UNLIT")
    if foreign_lights(trace, nodes):
        out.append("LIT_ATOM_FOREIGN")
    return out or ["CLEAN"]


def run(names: list[str]) -> dict[str, list[str]]:
    from app.explain_tree import build_nodes
    from app.opsin_trace import Trace, trace
    from app.token_owner import assign_owners

    results = {}
    for name in names:
        t = trace(name)
        if not isinstance(t, Trace):
            results[name] = [t.reason.upper()]
            continue
        try:
            nodes = build_nodes(t)
        except Exception:
            results[name] = ["NODE_ERROR"]
            continue
        results[name] = classify(t, nodes, assign_owners(t.tokens))
    return results


def _report(title: str, results: dict[str, list[str]]) -> int:
    counts = collections.Counter(o for outs in results.values() for o in outs)
    print(f"\n== {title}: {len(results)} names")
    for outcome in ("CLEAN", "UNREADABLE", "UNAVAILABLE", "MISMATCH", "UNPLACED", "NODE_ERROR", "PART_UNPLACED",
                    "ATOM_GAP", "ATOM_OVERLAP", "BAD_SPAN", "CROSSING", "LABEL_EDGE", "ORPHAN_TOKEN",
                    "HYDRO_WRONG", "STEREO_NO_PARENT", "STEREO_WRONG_ATOM", "LOCANT_UNLIT",
                    "LIT_ATOM_FOREIGN"):
        print(f"  {outcome:18s} {counts.get(outcome, 0)}")
    print("  residue:")
    for name, outs in results.items():
        if outs != ["CLEAN"]:
            print(f"    {','.join(outs):40s} {name}")
    return sum(v for k, v in counts.items() if k not in PASSING)


def main() -> int:
    from tests.conftest import GOLDEN_NAMES
    from tests.fixtures.explain_corpus import CURATED, FULL

    parser = argparse.ArgumentParser()
    parser.add_argument("--chembl", help="TSV of chembl_id<TAB>name (see build_chembl_fixture.py)")
    args = parser.parse_args()
    bad = _report("corpus", run(sorted({n for _, n in CURATED + FULL} | set(GOLDEN_NAMES))))
    if args.chembl:
        with open(args.chembl) as fh:
            names = [line.rstrip("\n").split("\t", 1)[1] for line in fh if "\t" in line]
        bad += _report("chembl", run(names))
    return 1 if bad else 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)   # the JVM would otherwise keep the process alive
