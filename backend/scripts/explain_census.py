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
  PART_CONTAINS_PART  one part's span strictly contains another part's span (a parent
                      label that swallows the substituents written inside it)
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
  LOCANT_WRONG_ATOM   a locant node inside its own part (not a substituent's leading
                      position, not hydro / anomer, which have their own checks) lights
                      an atom that does not carry that locant, primed per spiro
                      component (suffix-owned atoms excepted); see wrong_locant_atoms
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


def contained_parts(nodes) -> list:
    """(outer label, inner label) for every substituent / parent / suffix whose span
    strictly contains another such node's span. CROSSING sees only partial overlap and
    LABEL_EDGE only the ends, so a root label that runs across a neighbour's text
    ("epoxy-3-methoxy-17-methylmorphinan") passes both."""
    parts = [n for n in nodes if n["kind"] in PART_KINDS and n["span"]]
    out = []
    for a in parts:
        for b in parts:
            if a is not b and tuple(a["span"]) != tuple(b["span"]) \
                    and a["span"][0] <= b["span"][0] and b["span"][1] <= a["span"][1]:
                out.append((a["label"], b["label"]))
    return out


def _spiro_primes(trace, node, loc: str) -> int:
    """How many primes OPSIN puts on the atom a locant names. In
    spiro[A-x,y'-B] every locant written INSIDE the brackets after the spiro
    locants of THAT spiro system is a position of a later component, and OPSIN
    numbers those atoms 1', 2', ... (a second spiro locant makes the third
    component ''). A locant after the closing bracket ("spiro[...]-2(1H)-one",
    "-1-ium") is the first component's or the whole's, as written. A name may
    hold several spiro systems; only the one the node is written in counts.
    The gate demands an EXACT locant: a bare number in a later component, or a
    primed one after the bracket, is the wrong atom."""
    if loc.endswith("'") or not node["span"]:
        return 0
    start = node["span"][0]
    primes = 0
    for head in (t for t in trace.tokens if t.kind == "polyCyclicSpiro" and t.span[1] <= start):
        end = _close_of(trace.text, head.span[1])
        if end is not None and start < end:
            primes = sum(1 for t in trace.tokens if t.kind == "spiroLocant"
                         and head.span[1] <= t.span[0] and t.span[1] <= start)
    return primes


def _close_of(text: str, pos: int):
    """Index just past the bracket opening at text[pos], else None."""
    if pos >= len(text) or text[pos] not in "[({":
        return None
    depth = 0
    for k in range(pos, len(text)):
        if text[k] in "[({":
            depth += 1
        elif text[k] in "])}":
            depth -= 1
            if depth == 0:
                return k + 1
    return None


def _is_part_position_in_front(trace, node, parent) -> bool:
    """True when OPSIN placed the part at this very number (TracePart.locant) and
    the number is written in front of the part's group token: it is the position
    the part hangs on, not the part's own numbering, so a node that treats it as
    the part's own ("1-oxiranylpropan-2-one" lighting oxirane's O1, which also
    carries a 1) lights the wrong atom whatever that atom carries."""
    owns = set(parent["owns"])
    keys = {p.span for p in trace.parts if p.kind == "substituent" and p.atoms and set(p.atoms) <= owns}
    for key in keys:
        placed = {p.locant for p in trace.parts if p.span == key and p.locant}
        group = next((t for t in trace.tokens if t.owner == key and t.kind == "group"), None)
        if group is None or node["label"] not in placed or not node["span"] or node["span"][1] > group.span[0]:
            continue
        # Only where a replacement locant could be mistaken for it: the number
        # sits right before a heteroatom or an alkane stem ("1-oxiranyl",
        # "N-hexadecyl"); "[1,1'-biphenyl]" and "1,3-dioxolane" are the name's own.
        tok = next((t for t in trace.tokens if t.span[0] <= node["span"][0] and node["span"][1] <= t.span[1]), None)
        after = next((t for t in trace.tokens[tok.index + 1:]
                      if t.kind not in ("locant", "multiplier", "hyphen")), None) if tok is not None else None
        if after is not None and after.kind in ("heteroatom", "alkaneStemComponent"):
            return True
    return False


def wrong_locant_atoms(trace, nodes) -> list:
    """(label, atoms) for every locant node inside its own part that lights an
    atom not carrying that exact locant. LIT_ATOM_FOREIGN only asks whether the
    atom belongs to the part's family, so it cannot see a wrong atom of the right
    part. Exempt, each judged elsewhere: a substituent's leading position (its
    claim is the parent's or the copy's: LIT_ATOM_FOREIGN), hydro and
    indicated-hydrogen locants (HYDRO_WRONG), an anomer mark (proven from the
    molecule by the gate), a locant that lights nothing (LOCANT_UNLIT), a
    bracket's own locant (no part). The atoms a suffix owns carry no number."""
    by_id = {n["id"]: n for n in nodes}
    bad = []
    for n in nodes:
        if n["kind"] != "locant" or n["parent"] is None or not n["lights"]:
            continue
        line, parent = n["line"], by_id[n["parent"]]
        if "hydrogen" in line or "anomer" in line:
            continue
        if parent["kind"] == "substituent" and "this group is attached at position" in line:
            continue
        if parent["kind"] == "substituent" and _is_part_position_in_front(trace, n, parent):
            bad.append((n["label"], sorted(n["lights"])))      # the parent's position, read as the part's own
            continue
        want = n["label"] + "'" * _spiro_primes(trace, n, n["label"])
        free = set(parent["owns"]) if parent["kind"] == "suffix" else set()
        wrong = [a for a in n["lights"] if want not in trace.atoms[a].locants and a not in free]
        if wrong:
            bad.append((n["label"], sorted(n["lights"])))
    return bad


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
    if contained_parts(nodes):
        out.append("PART_CONTAINS_PART")
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
    if wrong_locant_atoms(trace, nodes):
        out.append("LOCANT_WRONG_ATOM")
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
                    "ATOM_GAP", "ATOM_OVERLAP", "BAD_SPAN", "CROSSING", "PART_CONTAINS_PART", "LABEL_EDGE", "ORPHAN_TOKEN",
                    "HYDRO_WRONG", "STEREO_NO_PARENT", "STEREO_WRONG_ATOM", "LOCANT_UNLIT",
                    "LIT_ATOM_FOREIGN", "LOCANT_WRONG_ATOM"):
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
