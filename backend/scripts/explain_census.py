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
                      anomeric carbon the structure cannot prove, and a number of a
                      fusion component's own numbering that no element / ring
                      evidence pins to one atom, light nothing by design and are
                      not counted)
  LOCANT_WRONG_ATOM   (a "4-O-" pair in front of a substituent must light the PARENT's O
                      and the parent carbon it is bonded to, never an atom of the
                      substituent itself; see app.explain_tree.oxy_pair_allowed)
                      (a fusion component's number must light an atom of the element it
                      puts in the ring, and, among several, one sharing a ring with its
                      siblings' atoms) a locant node inside its own part (not a substituent's leading
                      position, not hydro / anomer, which have their own checks) lights
                      an atom that does not carry that locant, primed per spiro
                      component (suffix-owned atoms excepted); see wrong_locant_atoms
  FUNCTION_SWALLOWED  a functional-class word ("ketone", "ether", "anhydride", "ester",
                      "oxime", "chloride") that no part node starts at: the word is
                      swallowed into the tail of the alkyl written before it ("ethyl
                      ketone"), or into a root, or has no node at all
  ALKYL_HETERO        a plain alkyl / aryl substituent ("methyl", "isobutyl", "phenyl")
                      owning a heteroatom: the atoms of a functional word, or of a suffix,
                      handed to the group written before it
  LINE_CLAIM_FALSE    a suffix line that says what its atoms are ("-C(=O)OH", "C=O",
                      "-C(=O)O-") when they are not, or a parent line whose prose does
                      not fit the number of atoms the parent holds
  SUFFIX_OWNS_H       a suffix node owning a hydrogen atom (an isotopic hydrogen of the
                      skeleton, handed to the characteristic group)
  OXIDATION_WRONG     an oxidation-number token ("(II)") that lights atoms other than the
                      part written right before it ("copper(II)" is the copper's)
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


def _component_for(trace, node):
    """(elements, k) when the node is a number of a fusion PREFIX component's own
    numbering ("[1,3]thiazolo[5,4-b]pyridine"): the elements the component's numbers
    put in the ring, in order, and this number's index (None when they cannot be
    paired). Read from the written tokens alone. None otherwise (also inside spiro
    brackets, whose primed numbering has its own rule)."""
    from app.label_rules import LOCANT_KINDS, fusion_component_elements, locant_items
    if node["kind"] != "locant" or not node["span"]:
        return None
    start = node["span"][0]
    tok = next((t for t in trace.tokens if t.kind in LOCANT_KINDS and t.span[0] <= start < t.span[1]), None)
    if tok is None:
        return None
    for head in (t for t in trace.tokens if t.kind == "polyCyclicSpiro" and t.span[1] <= start):
        end = _close_of(trace.text, head.span[1])
        if end is not None and start < end:
            return None
    elements = fusion_component_elements(trace.tokens, tok.index, trace.text)
    if elements is None:
        return None
    labels = [x for x, _ in locant_items(trace.text, tok.span)]
    return elements, (labels.index(node["label"]) if len(labels) == len(elements) and node["label"] in labels
                      else None), tok.span


def _provable_atoms(trace, part, elements, k) -> list:
    """The atom the k-th number of a fusion component names, when the element and the
    rings prove it (else []): an element occurring once in the part is the
    component's; among several, the one atom of that element sharing a ring with the
    atoms proven that way. Written here, not shared with the builder."""
    from rdkit import Chem
    if k is None or elements[k] is None:
        return []
    mol = Chem.MolFromSmiles(trace.smiles)
    if mol is None:
        return []
    of = lambda e: [a for a in part if trace.atoms[a].element == e]
    anchors = [of(e)[0] for e in set(elements) if e is not None and elements.count(e) == 1 and len(of(e)) == 1]
    e = elements[k]
    if elements.count(e) != 1:
        return []
    if len(of(e)) == 1:
        return of(e)
    rings = [set(r) for r in mol.GetRingInfo().AtomRings()]
    near = [a for a in of(e) if anchors and all(any({a, s} <= r for r in rings) for s in anchors)]
    return near if len(near) == 1 else []


def _component_part(nodes, node) -> list:
    return [a for n in nodes if n["id"] == node["parent"] for a in n["owns"]]


def _component_wrong(trace, nodes, node, comp) -> bool:
    """True when a fusion-component number lights anything but what is proven: the
    one provable atom, or nothing when none is provable."""
    elements, k, _ = comp
    return sorted(node["lights"]) != sorted(_provable_atoms(trace, _component_part(nodes, node), elements, k))


def _unproven_component_number(trace, nodes, node) -> bool:
    """True for a number of a fusion component's own numbering that the element and
    the rings cannot pin to one atom: lighting nothing is correct and not a LOCANT_UNLIT."""
    comp = _component_for(trace, node)
    return comp is not None and not _provable_atoms(trace, _component_part(nodes, node), comp[0], comp[1])


def _locant_token(trace, node):
    from app.label_rules import LOCANT_KINDS
    if not node["span"]:
        return None
    # (a bare number can be split out of a stereo token: "3alpha,21-dihydroxy")
    kinds = LOCANT_KINDS | {"stereoChemistry"}
    return next((t for t in trace.tokens if t.kind in kinds and t.span[0] <= node["span"][0] < t.span[1]), None)


def _written_next(trace, tok):
    """The token the locant run before `tok` is written for: the next one that is not a
    locant, counting word or hyphen."""
    return next((t for t in trace.tokens[tok.index + 1:] if t.kind not in ("locant", "multiplier", "hyphen")), None)


def _position_in_front(trace, node, parent):
    """(part key, whether OPSIN placed the part at this number) when the node is a
    substituent's leading position: written for the start of the part's name
    (resolve_roles' prefix role) and not name-building. A number before a heteroatom / ring token builds the name
    ("1,3-dioxolanyl") unless OPSIN placed the part at that very number
    (TracePart.locant: "1-oxiranylpropan-2-one"). Read from tokens and parts only."""
    from app.label_rules import _BUILDS_NAME
    tok = _locant_token(trace, node)
    if tok is None:
        return None
    owns = set(parent["owns"])
    after = _written_next(trace, tok)
    for key in {p.span for p in trace.parts if p.kind == "substituent" and p.atoms and set(p.atoms) <= owns}:
        placed = {p.locant for p in trace.parts if p.span == key and p.locant}
        if after is not None and after.kind in ("heteroatom", "alkaneStemComponent") and node["label"] in placed:
            return key, True                  # "1-oxiranyl", "N-hexadecyl": not a replacement locant
        if after is None or after.kind not in _BUILDS_NAME:
            return key, node["label"] in placed
    return None


def _union_of_copies(trace, key, lights) -> bool:
    copies = [set(p.atoms) for p in trace.parts if p.span == key]
    lit, rest = set(lights), set(lights)
    for c in copies:
        if c <= lit:
            rest -= c
    return not rest


def _suffix_attachment_locants(trace, nodes, suffix) -> set:
    """The numbers a suffix may carry: those of the atoms its own atoms are bonded to."""
    from rdkit import Chem
    mol = Chem.MolFromSmiles(trace.smiles)
    own = set(suffix["owns"])
    return {loc for a in own for nb in mol.GetAtomWithIdx(a).GetNeighbors() if nb.GetIdx() not in own
            for loc in trace.atoms[nb.GetIdx()].locants}


def wrong_locant_atoms(trace, nodes) -> list:
    """(label, atoms) for every locant node inside its own part that lights an
    atom not carrying that exact locant. LIT_ATOM_FOREIGN only asks whether the
    atom belongs to the part's family, so it cannot see a wrong atom of the right
    part. Exempt, each judged elsewhere and decided from tokens and parts, never from
    a node's wording: a locant written for a hydro prefix (HYDRO_WRONG), an
    alpha / beta mark of a carbohydrate (proven from the molecule by the gate), a
    locant that lights nothing (LOCANT_UNLIT), a bracket's own locant (no part).
    A substituent's leading position must light a whole copy of the part, or atoms
    outside it (a part OPSIN placed at the number is never one of its own atoms),
    or an own atom that carries the number (a ring's attachment). A suffix's
    number must be one of the numbers its atoms are bonded to. A fusion component's
    own number lights exactly the atom the element and rings prove, else nothing.
    The atoms a suffix owns carry no number."""
    from app.explain_tree import oxy_pair_allowed
    by_id = {n["id"]: n for n in nodes}
    carbohydrate = any(t.kind == "carbohydrateRingSize" for t in trace.tokens)
    bad = []
    for n in nodes:
        if n["kind"] != "locant":
            continue
        parent = by_id[n["parent"]] if n["parent"] is not None else None
        pair = oxy_pair_allowed(trace, n, parent, nodes)
        if pair is not None:
            if not set(n["lights"]) <= pair:
                bad.append((n["label"], sorted(n["lights"])))
            continue
        if parent is None:
            continue
        tok = _locant_token(trace, n)
        comp = _component_for(trace, n)
        if comp is not None:
            if _component_wrong(trace, nodes, n, comp):
                bad.append((n["label"], sorted(n["lights"])))
            continue
        if not n["lights"]:
            continue
        target = _written_next(trace, tok) if tok is not None else None
        if target is not None and target.kind == "hydro":
            continue
        if carbohydrate and n["label"].lower() in ("alpha", "beta"):
            continue
        want = n["label"] + "'" * _spiro_primes(trace, n, n["label"])
        carries = all(want in trace.atoms[a].locants for a in n["lights"])
        if parent["kind"] == "substituent":
            pos = _position_in_front(trace, n, parent)
            if pos is not None:
                key, placed = pos
                outside = not set(n["lights"]) & set(parent["owns"])
                ok = outside or _union_of_copies(trace, key, n["lights"]) or (carries and not placed)
                if not ok:
                    bad.append((n["label"], sorted(n["lights"])))
                continue
        if parent["kind"] == "suffix":
            own = set(parent["owns"])
            if n["label"] not in _suffix_attachment_locants(trace, nodes, parent) or not all(
                    want in trace.atoms[a].locants or a in own for a in n["lights"]):
                bad.append((n["label"], sorted(n["lights"])))
            continue
        if not carries:
            bad.append((n["label"], sorted(n["lights"])))
    return bad


FUNCTIONAL_KINDS = ("functionalGroup", "functionalClass")
_HYDROCARBON_RADICAL = re.compile(
    r"^(?:\d+(?:,\d+)*-)?(?:n-|iso|tert-|sec-|neo)?"
    r"(?:(?:meth|eth|prop|but|pent|hex|hept|oct|non|dec|undec|dodec)yl|phenyl|benzyl|vinyl|allyl|"
    r"cyclo(?:prop|but|pent|hex|hept|oct)yl|naphthyl)$")


def swallowed_functional_words(trace, nodes) -> list:
    """The functional-class words no part node starts at. A word's node may start at
    the locants / counting word written right before it ("1,1-dioxide"), or at the
    first of several words written together ("ketone oxime")."""
    parts = [n for n in nodes if n["kind"] in PART_KINDS and n["span"]]
    out = []
    for tok in trace.tokens:
        if tok.kind not in FUNCTIONAL_KINDS:
            continue
        starts, j = {tok.span[0]}, tok.index - 1
        while j >= 0 and trace.tokens[j].kind in ("locant", "multiplier", "hyphen") + FUNCTIONAL_KINDS:
            starts.add(trace.tokens[j].span[0])
            j -= 1
        holders = [n for n in parts if n["span"][0] <= tok.span[0] and tok.span[1] <= n["span"][1]]
        if not any(n["span"][0] in starts for n in holders):
            out.append(trace.text[tok.span[0]:tok.span[1]])
    return out


def alkyl_owning_heteroatoms(trace, nodes) -> list:
    """(label, elements) for every plain alkyl / aryl substituent that owns an atom
    that is neither carbon nor hydrogen (an isotopic hydrogen is the group's own)."""
    out = []
    for n in nodes:
        if n["kind"] == "substituent" and _HYDROCARBON_RADICAL.match(n["label"].lower()):
            odd = sorted({trace.atoms[a].element for a in n["owns"] if trace.atoms[a].element not in ("C", "H")})
            if odd:
                out.append((n["label"], odd))
    return out


def _claim_true(claim, mol, owns) -> bool:
    """Whether the atoms a suffix owns are what its line says. Written here, not shared
    with the glossary: look at every carbon next to an owned oxygen."""
    from rdkit import Chem
    owned_o = {a for a in owns if a < mol.GetNumAtoms() and mol.GetAtomWithIdx(a).GetSymbol() == "O"}
    carbons = {n.GetIdx() for o in owned_o for n in mol.GetAtomWithIdx(o).GetNeighbors() if n.GetSymbol() == "C"}
    for c in carbons:
        kinds = {o: mol.GetBondBetweenAtoms(c, o).GetBondType() for o in owned_o if mol.GetBondBetweenAtoms(c, o)}
        double = [o for o, b in kinds.items() if b == Chem.BondType.DOUBLE]
        single = [o for o, b in kinds.items() if b == Chem.BondType.SINGLE]
        if claim == "carbonyl" and double:
            return True
        if claim == "carboxylate" and double and single:
            return True
        # (no table line claims an ester today; the check stays so the class stays visible:
        # "sodium acetate" has the -C(=O)O- of an ester and none of its second carbon)
        if claim == "ester" and double and any(mol.GetAtomWithIdx(o).GetDegree() >= 2 for o in single):
            return True
        if claim == "acid" and double and any(mol.GetAtomWithIdx(o).GetDegree() == 1 for o in single):
            return True
    return False


def false_line_claims(trace, nodes) -> list:
    """(label, line) for every suffix line that asserts what its atoms are when they
    are not, and every parent line whose prose does not fit its atom count. Whether a
    node asserts the claim is read from the glossary's own output, never from wording
    typed here."""
    from rdkit import Chem
    from app import glossary
    mol = Chem.MolFromSmiles(trace.smiles)
    out = []
    for n in nodes:
        if n["kind"] == "suffix" and mol is not None:
            claim = glossary.suffix_claim(n["label"])
            asserted = n["line"] == glossary.describe_part("suffix", n["label"], None, len(set(n["owns"])))
            if claim and asserted and not _claim_true(claim, mol, n["owns"]):
                out.append((n["label"], n["line"]))
        elif n["kind"] == "parent":
            claim = glossary.parent_claim(n["label"])
            copies = n.get("copies", 1) or 1
            total = len(set(n["owns"]))
            per_copy = total // copies if copies > 1 and total % copies == 0 else total
            if claim and claim[0] in n["line"] and not claim[1][0] <= per_copy <= claim[1][1]:
                out.append((n["label"], n["line"]))
    return out


def oxidation_numbers_misplaced(trace, nodes) -> list:
    """Oxidation-number tokens ("(II)") whose node lights atoms other than the part
    written right before them."""
    out = []
    for tok in trace.tokens:
        if tok.kind != "oxidationNumberSpecifier":
            continue
        before = next((n for n in nodes if n["kind"] in PART_KINDS and n["span"] and n["span"][1] == tok.span[0]), None)
        mine = [n for n in nodes if n["span"] and tuple(n["span"]) == tok.span and n["kind"] not in PART_KINDS]
        if before is None or any(not set(n["lights"]) <= set(before["owns"]) for n in mine):
            out.append(trace.text[tok.span[0]:tok.span[1]])
    return out


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
           and not _unproven_component_number(trace, nodes, n) for n in nodes):
        out.append("LOCANT_UNLIT")
    if foreign_lights(trace, nodes):
        out.append("LIT_ATOM_FOREIGN")
    if wrong_locant_atoms(trace, nodes):
        out.append("LOCANT_WRONG_ATOM")
    if swallowed_functional_words(trace, nodes):
        out.append("FUNCTION_SWALLOWED")
    if alkyl_owning_heteroatoms(trace, nodes):
        out.append("ALKYL_HETERO")
    if false_line_claims(trace, nodes):
        out.append("LINE_CLAIM_FALSE")
    if any(n["kind"] == "suffix" and any(trace.atoms[a].element == "H" for a in n["owns"]) for n in nodes):
        out.append("SUFFIX_OWNS_H")
    if oxidation_numbers_misplaced(trace, nodes):
        out.append("OXIDATION_WRONG")
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
                    "LIT_ATOM_FOREIGN", "LOCANT_WRONG_ATOM", "FUNCTION_SWALLOWED", "ALKYL_HETERO",
                    "LINE_CLAIM_FALSE", "SUFFIX_OWNS_H", "OXIDATION_WRONG"):
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
