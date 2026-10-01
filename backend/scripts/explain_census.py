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
                      substituent itself; see app.explain_gate.oxy_pair_allowed)
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
                      chain is bonded to (app.explain_gate.foreign_lights)
  HOVER_LINE_FALSE    a hover line that says something false about the molecule on screen:
                      a group's hydrogens ("methyl" in hydroxymethyl), a hydro / indicated
                      hydrogen on an atom with none, a spiro descriptor, an anomer's group,
                      a stereo mark's meaning, a parent that is not the only core or not
                      the benzene ring its prose names, an isotope label's positions; or a
                      line using such a claim's words in a shape the check does not know
                      (see false_hover_lines)
Every outcome except CLEAN and UNREADABLE fails the run (exit 1).
"""

import argparse
import collections
import os
import re
import sys
from typing import Optional

from rdkit import Chem

from app import glossary, opsin_trace
from app.explain_gate import foreign_lights, oxy_pair_allowed
from app.explain_tree import build_nodes, stereo_atoms
from app.label_rules import (
    BARE_DESCRIPTOR, BUILDS_NAME, LOCANT_KINDS, STEREO_MARK, fusion_component_elements, locant_items,
)
from app.opsin_trace import Trace
from app.token_owner import assign_owners, bracket_end

PART_KINDS = ("substituent", "parent", "suffix")
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
        end = bracket_end(trace.text, head.span[1])
        if end is not None and start < end:
            primes = sum(1 for t in trace.tokens if t.kind == "spiroLocant"
                         and head.span[1] <= t.span[0] and t.span[1] <= start)
    return primes


def _component_for(trace, node):
    """(elements, k) when the node is a number of a fusion PREFIX component's own
    numbering ("[1,3]thiazolo[5,4-b]pyridine"): the elements the component's numbers
    put in the ring, in order, and this number's index (None when they cannot be
    paired). Read from the written tokens alone. None otherwise (also inside spiro
    brackets, whose primed numbering has its own rule)."""
    if node["kind"] != "locant" or not node["span"]:
        return None
    start = node["span"][0]
    tok = next((t for t in trace.tokens if t.kind in LOCANT_KINDS and t.span[0] <= start < t.span[1]), None)
    if tok is None:
        return None
    for head in (t for t in trace.tokens if t.kind == "polyCyclicSpiro" and t.span[1] <= start):
        end = bracket_end(trace.text, head.span[1])
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
    tok = _locant_token(trace, node)
    if tok is None:
        return None
    owns = set(parent["owns"])
    after = _written_next(trace, tok)
    for key in {p.span for p in trace.parts if p.kind == "substituent" and p.atoms and set(p.atoms) <= owns}:
        placed = {p.locant for p in trace.parts if p.span == key and p.locant}
        if after is not None and after.kind in ("heteroatom", "alkaneStemComponent") and node["label"] in placed:
            return key, True                  # "1-oxiranyl", "N-hexadecyl": not a replacement locant
        if after is None or after.kind not in BUILDS_NAME:
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
    by_id = {n["id"]: n for n in nodes}
    carbohydrate = any(t.kind == "carbohydrateRingSize" for t in trace.tokens)
    mol = Chem.MolFromSmiles(trace.smiles)
    bad = []
    for n in nodes:
        if n["kind"] != "locant":
            continue
        parent = by_id[n["parent"]] if n["parent"] is not None else None
        pair = oxy_pair_allowed(trace, n, parent, nodes, mol)
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
    mol = Chem.MolFromSmiles(trace.smiles)
    out = []
    for n in nodes:
        if n["kind"] == "suffix" and mol is not None:
            claim = glossary.suffix_claim(n["label"])
            asserted = n["line"] == glossary.describe_part("suffix", n["label"], len(set(n["owns"])))
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


# ---- HOVER_LINE_FALSE ----------------------------------------------------------------
# What each hover sentence says about the molecule on screen, checked against that
# molecule. Written here, not shared with app.glossary: the claims are read from the
# sentence itself (a check of what a sentence says must read the sentence) and every
# fact is measured with RDKit by this module's own rules, so a wrong rule in the
# glossary cannot also hide here. A line that uses the vocabulary of a claim this
# check knows ("hydrogen", "CH3", "on its own", "anomer", "mirror-image", ...) in a
# shape it does not recognise is itself reported: a reworded table line cannot slip
# past unchecked. A line with no such vocabulary claims nothing checkable and passes.

_NOT_CORES = re.compile(r"^(?:(?:mono|di|tri|tetra|penta|hexa|hepta|octa|nona|deca|hemi|sesqui)?hydrate"
                        r"|hydrochloride|hydrobromide|hydroiodide|hydrofluoride)$", re.IGNORECASE)
_QUOTED = re.compile(r'"[^"]*"')
_VOCAB = re.compile(r"hydrogen|\bCH3\b|\bNH2\b|on its own|anomer|mirror-image|shared|share one|"
                    r"positions it names|position number|built around|cores this name|benzene ring|"
                    r"stereocentre|double bond|optical rotation|Fischer|configuration prefix")
# The bare group each checked label names: (element, which atoms, hydrogens per atom in
# one copy). "end": a carbon not bonded to the group's own oxygen (acetyl's CH3 end).
_BARE_GROUP = {
    "methyl": ("C", "all", (3,)), "ethyl": ("C", "all", (3, 2)), "methoxy": ("C", "all", (3,)),
    "ethoxy": ("C", "all", (3, 2)), "acetyl": ("C", "end", (3,)), "acetyloxy": ("C", "end", (3,)),
    "amino": ("N", "all", (2,)), "hydroxy": ("O", "all", (1,)),
}
_AMINE_ENDING = re.compile(r"^(?:di|tri|tetra)?amine$")
_OLD_FORMULA = re.compile(r"(?:\bCH3\b|-NH2|-OH|-O-CH3|-O-CH2CH3|CH3-CH2-|CH3-C\(=O\)-|-O-C\(=O\)-CH3) group"
                          r"|three hydrogens")
_CLAUSE = re.compile(r"Here (?:its|the|each of its|each of the) (?:end )?(carbon|nitrogen|oxygen)s? carr(?:y|ies) "
                     r"(no hydrogen|1 hydrogen|\d+ hydrogens|[\d, ]+ and \d+ hydrogens)(; other groups take the rest)?\.")


# The vocabulary-bearing phrases a true line may contain, written out here (not imported). A line
# is checked twice: its recognised claim is measured, then these phrases are cut out and any claim
# vocabulary still left over is a claim nothing checked.
_PHRASES = [re.compile(p) for p in (
    r"\((?:[^()]|\([^()]*\))*?on its own\)",                                  # a bare group's formula
    _CLAUSE.pattern,                                                              # the hydrogens a group's atoms carry
    r"an =N-NH(?:-C\(=O\)-NH2|2) group in place of the carbonyl oxygen",
    r"Position \S+ — the \S+ atom carries a hydrogen here\.",
    r"Position \S+ — the name puts a hydrogen (?:at this position|on the \S+ atom)"
    r"(?:; here (?:a group or bond named elsewhere takes its place|that atom carries none))?\.",
    r"Position \S+ — a hydrogen is fixed here\.",
    r"records that hydrogens were added here, which fixes where the double bonds go",
    r"pins which ring atom carries a hydrogen",
    r"is the core skeleton the rest of the name is built around",
    r"It is the core the rest of the name is built around",
    r"one of the \w+ cores this name is built from",
    r"two fused benzene rings", r"a benzene ring fused to", r"a benzene ring attached by one of its carbons",
    r"is a benzene ring\.", r"is a benzene ring attached", r"a benzene ring\b(?= *$)",
    r"names two rings that share one atom", r"names rings that share single atoms",
    r"names rings joined at single shared atoms", r"marks one atom shared between two rings",
    r"fixes the three-dimensional arrangement at the positions it names",
    r"fixes the three-dimensional arrangement at one stereocentre; the mark itself carries no position number",
    r"the arrangement at (?:the positions? it names|one stereocentre) only as a relative arrangement, not an "
    r"absolute one; it does not say which of the two mirror-image forms is meant",
    r"says the marks of its set give only a relative arrangement; it does not say which of the two "
    r"mirror-image forms is meant",
    r"is written inside a racemate mark \(rac\): the name means an equal mix of this form and its mirror image",
    r"marks a racemate: an equal mix of the two mirror-image forms",
    r"gives the sign of optical rotation: this form turns polarised light to the (?:left|right)\. It does not by "
    r"itself say how the atoms are arranged",
    r"is a Fischer label: it puts the part named after it in the [DL] series, by comparing one of its "
    r"stereocentres with [DL]-glyceraldehyde",
    r"says two groups lie on (?:the same side|opposite sides) of the ring or double bond they are on",
    r"fixes the arrangement at one double bond: its higher-ranked groups lie on (?:the same side|opposite sides)"
    r"\. The mark itself carries no position number",
    r"is a sugar configuration prefix: the stereocentres? it covers (?:is|are) arranged as in \w+",
    r"is a stereo descriptor: part of how the name gives the three-dimensional arrangement",
    r"names the anomer: which way the group on the ring carbon next to the ring [^,]+? points, relative to the "
    r"sugar's reference stereocentre",
    r"is an isotope label: it says which isotope sits at the positions it names",
    r"is an isotope label: it says which isotope the part named after it carries in place of the usual one; "
    r"the label gives no position number",
    r"its plain numbers count the atoms between them, in order along the system, and a raised number is a "
    r"position, not a count",
    r"hydrochloric acid \(HCl\)|hydrobromic acid \(HBr\)|hydroiodic acid \(HI\)|hydrofluoric acid \(HF\)",
)]


def _unchecked_claim(line: str) -> bool:
    """True when claim vocabulary is left in `line` after the quoted text and every phrase this
    module knows how to read has been cut out."""
    rest = _QUOTED.sub("", line)
    for phrase in _PHRASES:
        rest = phrase.sub("", rest)
    return bool(_VOCAB.search(rest))


def _h(mol, i: int) -> int:
    return mol.GetAtomWithIdx(i).GetTotalNumHs(includeNeighbors=True)


def _heavy_degree(mol, i: int) -> int:
    return sum(1 for n in mol.GetAtomWithIdx(i).GetNeighbors() if n.GetAtomicNum() > 1)


def _said_counts(text: str) -> list[int]:
    if text == "no hydrogen":
        return [0]
    return [int(x) for x in re.findall(r"\d+", text)]


def _group_line_problem(mol, node, element, which, bare) -> Optional[str]:
    """A table line for a group with a bare formula: what it says the atoms carry must
    be what they carry. The bare formula alone ("an -NH2 group", "three hydrogens") is a
    claim about these atoms; "(-NH2 on its own)" promises a measured clause whenever the
    atoms differ from the bare group."""
    atoms = [a for a in sorted(set(node["owns"])) if mol.GetAtomWithIdx(a).GetSymbol() == element]
    if which == "end":       # not the carbon bonded to the group's own oxygen(s)
        own = set(node["owns"])
        atoms = [a for a in atoms if not any(n.GetSymbol() == "O" and n.GetIdx() in own
                                             for n in mol.GetAtomWithIdx(a).GetNeighbors())]
    actual = sorted((_h(mol, a) for a in atoms), reverse=True)
    per = len(actual) if len(bare) == 1 else max(node.get("copies") or 1, 1)
    expected = sorted(bare * per, reverse=True)
    body = _QUOTED.sub("", node["line"])
    said = _CLAUSE.search(body)
    if _OLD_FORMULA.search(body) and actual != expected:
        return f"names the bare group, atoms carry {actual}"
    if "free hydrogens" in body and not all(x >= 1 for x in actual):
        return f"free hydrogens, atoms carry {actual}"
    if said:
        counts = _said_counts(said.group(2))
        each = "each of" in said.group(0)
        if (each and any(x != counts[0] for x in actual)) or (not each and counts != actual):
            return f"says {said.group(2)}, atoms carry {actual}"
        if said.group(3):
            plain = all(mol.GetAtomWithIdx(a).GetNumRadicalElectrons() == 0 and mol.GetAtomWithIdx(a).GetFormalCharge() == 0
                        for a in atoms)
            if not (plain and len(actual) == len(expected) and all(x <= e for x, e in zip(actual, expected))):
                return "other groups take the rest, but an atom carries more or is charged"
    elif "on its own" in body:
        if actual != expected:
            return f"bare group only, atoms carry {actual}"
    elif not _OLD_FORMULA.search(body) and "free hydrogens" not in body and _VOCAB.search(body):
        return "a claim this check does not recognise"
    return None


_H_LOCANT = [
    (re.compile(r"^Position (\S+) — the ([A-Z][a-z]?)(\S+) atom carries a hydrogen here\.$"), "has"),
    (re.compile(r"^Position (\S+) — the name puts a hydrogen on the ([A-Z][a-z]?)(\S+) atom; here a group or bond "
                r"named elsewhere takes its place\.$"), "taken"),
    (re.compile(r"^Position (\S+) — the name puts a hydrogen on the ([A-Z][a-z]?)(\S+) atom; here that atom "
                r"carries none\.$"), "none"),
    (re.compile(r"^Position (\S+) — the name puts a hydrogen on the ([A-Z][a-z]?)(\S+) atom\.$"), "said"),
]


def _h_locant_problem(mol, node) -> tuple[bool, Optional[str]]:
    """(recognised, problem) for a hydro / indicated / added hydrogen locant line."""
    line = node["line"]
    if re.match(r"^Position \S+ — the name puts a hydrogen at this position\.$", line):
        return True, None
    if re.match(r"^Position \S+ — a hydrogen is fixed here\.$", line):
        lit = node["lights"]
        return True, (None if lit and all(_h(mol, a) >= 1 for a in lit) else "a hydrogen is fixed here, none is")
    for shape, says in _H_LOCANT:
        m = shape.match(line)
        if not m:
            continue
        lit = node["lights"]
        if len(lit) != 1 or mol.GetAtomWithIdx(lit[0]).GetSymbol() != m.group(2):
            return True, f"names the {m.group(2)} atom, lights {len(lit)}"
        a = lit[0]
        bond = any(b.GetBondType() in (Chem.BondType.DOUBLE, Chem.BondType.TRIPLE)
                   for b in mol.GetAtomWithIdx(a).GetBonds())
        if says == "has" and _h(mol, a) < 1:
            return True, "carries a hydrogen here, it carries none"
        atom = mol.GetAtomWithIdx(a)
        charged = bool(atom.GetFormalCharge() or atom.GetNumRadicalElectrons())
        if says == "taken" and (charged or _h(mol, a) != 0 or not (_heavy_degree(mol, a) >= 3 or bond)):
            return True, "something takes the hydrogen's place, nothing does"
        if says == "none" and _h(mol, a) != 0:
            return True, "carries none, it carries one"
        return True, None
    return False, None


def _spiro_problem(mol, node) -> tuple[bool, Optional[str]]:
    m = re.fullmatch(r"spiro\[([^\]]*)\]", node["label"])
    if not m:
        return False, None
    numbers = m.group(1).split(".")
    line = node["line"]
    if "marks one atom shared between two rings" in line:
        return True, (None if len(node["lights"]) == 1 and len(numbers) == 2 else
                      f"one shared atom, lights {len(node['lights'])} ({len(numbers)} numbers)")
    two = re.search(r"names two rings that share one atom; (\d+) and (\d+) count the other atoms in each ring", line)
    if two:
        if len(numbers) != 2 or [two.group(1), two.group(2)] != numbers:
            return True, "monospiro line on another descriptor"
        lit = set(node["lights"])
        a, b = int(numbers[0]) + 1, int(numbers[1]) + 1
        rings = [set(r) for r in mol.GetRingInfo().AtomRings() if set(r) <= lit]
        if not any(len(r) == a and len(s) == b and len(r & s) == 1 for r in rings for s in rings if r is not s):
            return True, "no two lit rings of those sizes share one atom"
        return True, None
    if "names rings joined at single shared atoms" in line:
        if len(numbers) <= 2:
            return True, "polyspiro line on a two-number descriptor"
        if ("a raised number is a position" in line) != ("^" in node["label"]):
            return True, "raised numbers are positions, not counts, and only when the descriptor has them"
        return True, None
    if "names rings that share single atoms" in line:
        return True, None
    return False, None


def _ring_hetero_problem(mol, nodes, node) -> Optional[str]:
    """The base anomer line says which atom closes the sugar's ring ("the ring oxygen",
    "the ring sulfur"); the ring is read from the lit carbon, else from the rings inside the
    part that owns the mark."""
    line = node["line"]
    said = {"oxygen": "O", "sulfur": "S", "nitrogen": "N", "selenium": "Se"}
    m = re.search(r"next to the ring (oxygen|sulfur|nitrogen|selenium|(\w+) atom) points", line)
    if not m:
        return None
    want = said.get(m.group(1), m.group(2))
    lit = node["lights"]
    if len(lit) == 1:
        c = mol.GetAtomWithIdx(lit[0])
        ring = {n.GetSymbol() for n in c.GetNeighbors() if n.GetAtomicNum() > 1
                and mol.GetBondBetweenAtoms(lit[0], n.GetIdx()).IsInRing() and n.GetSymbol() != "C"}
    else:
        owner = next((n for n in nodes if n["id"] == node["parent"]), None)
        pool = set(owner["owns"]) if owner else set(range(mol.GetNumAtoms()))
        ring = set()
        for r in mol.GetRingInfo().AtomRings():
            if len(r) in (5, 6) and set(r) <= pool:
                odd = [mol.GetAtomWithIdx(i).GetSymbol() for i in r if mol.GetAtomWithIdx(i).GetSymbol() != "C"]
                if len(odd) == 1:
                    ring.add(odd[0])
    return None if want in ring else f"a ring {want} next to the anomeric carbon, the ring has {sorted(ring) or 'none'}"


def _anomer_problem(mol, node, nodes=()) -> tuple[bool, Optional[str]]:
    line = node["line"]
    if "names the anomer" not in line:
        return False, None
    ring_why = _ring_hetero_problem(mol, nodes, node)
    if ring_why:
        return True, ring_why
    lit = node["lights"]
    outside = []
    if len(lit) == 1:
        c = mol.GetAtomWithIdx(lit[0])
        outside = [n for n in c.GetNeighbors() if n.GetAtomicNum() > 1
                   and not mol.GetBondBetweenAtoms(lit[0], n.GetIdx()).IsInRing()]
    o = [n for n in outside if n.GetSymbol() == "O"]
    if "the OH on the ring carbon" in line:
        ok = len(o) == 1 and _h(mol, o[0].GetIdx()) >= 1 and _heavy_degree(mol, o[0].GetIdx()) == 1
        return True, None if ok else "an OH at the anomeric carbon, there is none"
    if "Here that group is an OH." in line:
        ok = len(o) == 1 and _h(mol, o[0].GetIdx()) >= 1 and _heavy_degree(mol, o[0].GetIdx()) == 1
        return True, None if ok else "an OH, there is none"
    joins = re.search(r"Here that group is the (\w+) that joins the sugar to the rest of the name\.", line)
    if joins:
        if joins.group(1) == "O":
            ok = len(o) == 1 and _heavy_degree(mol, o[0].GetIdx()) >= 2
        else:
            ok = (not o and len(outside) == 1 and outside[0].GetSymbol() == joins.group(1)
                  and _heavy_degree(mol, outside[0].GetIdx()) >= 2)
        return True, None if ok else f"joined through {joins.group(1)}, it is not"
    lone = re.search(r"Here that group is an? (\w+) atom\.", line)
    if lone:
        ok = (not o and len(outside) == 1 and outside[0].GetSymbol() == lone.group(1)
              and _heavy_degree(mol, outside[0].GetIdx()) == 1)
        return True, None if ok else f"a lone {lone.group(1)} atom, it is not"
    if "Here" in line:
        return False, None
    return True, None


_STEREO_LOC = r"(?:\d+[a-z]?'*|[A-Z][a-z]?'*)"
_LOCATED_MARK = re.compile(rf"^{_STEREO_LOC}(?:[RSrs]|[EZ]|alpha|beta)$")
_SUGAR_PREFIXES = {"glycero", "erythro", "threo", "arabino", "lyxo", "ribo", "xylo", "allo", "altro", "galacto",
                   "gluco", "gulo", "ido", "manno", "talo"}


def _stereo_set_word(trace, node) -> Optional[str]:
    """"rel" or "rac" when the mark is governed by one. The word covers the whole compound
    (IUPAC P-93.1.3), so any stereo token of the name that is a "rel-(...)" / "rac-(...)" or a
    lone "rel-" / "(rac)-" counts; the nearest one wins (the mark's own token, a touching one,
    then the nearest before, then after)."""
    if not node["span"]:
        return None
    toks = [t for t in trace.tokens if t.kind == "stereoChemistry"]
    here = next((t for t in toks if t.span[0] <= node["span"][0] < t.span[1]), None)
    if here is None:
        return None
    piece = lambda t: trace.text[t.span[0]:t.span[1]]
    own = re.match(r"^\s*\(?(rel|rac)\)?-?\(", piece(here), re.IGNORECASE)
    if own:
        return own.group(1).lower()
    if re.fullmatch(r"\s*\(?(rel|rac)\)?-?\s*", piece(here), re.IGNORECASE):
        return None
    found = []
    for j, other in enumerate(toks):
        if other is here:
            continue
        w = (re.match(r"^\s*\(?(rel|rac)\)?-?\(", piece(other), re.IGNORECASE)
             or re.fullmatch(r"\s*\(?(rel|rac)\)?-?\s*", piece(other), re.IGNORECASE))
        if w:
            touching = other.span[1] == here.span[0] or other.span[0] == here.span[1]
            k = toks.index(here)
            found.append((0 if touching else 1 if j < k else 2, abs(j - k), w.group(1).lower()))
    return min(found)[2] if found else None


def _marks_follow(trace, node) -> bool:
    """Whether a stereo mark is written after `node` inside its own token ("rel-(1R,2S)-")."""
    if not node["span"]:
        return True
    return bool(re.match(r"-?\s*\(", trace.text[node["span"][1]:]))


def _stereo_problem(trace, node) -> tuple[bool, Optional[str]]:
    """(recognised, problem) for a stereo mark's line. Each phrase below is a claim about
    the mark; the claim must fit the kind of mark the label is, read here from the label
    and the set it is written in."""
    label, line = node["label"], node["line"]
    word = _stereo_set_word(trace, node)
    located = bool(_LOCATED_MARK.match(label))
    bare = label in ("R", "S")
    racemic = label in ("rac", "RS", "SR", "+-", "±", "DL") or bool(re.fullmatch(r"\d+[a-z]?'*(?:RS|SR)", label))
    absolute_in_rel = word == "rel" and located and label[-1] not in "RS"      # E, Z, r, s, alpha, beta
    relative = label == "rel" or label.endswith("*") or (word == "rel" and (located or bare) and not absolute_in_rel)
    claims = [
        ("fixes the three-dimensional arrangement at the positions it names",
         located and not racemic and (word is None or absolute_in_rel)),
        ("marks a racemate: an equal mix of the two mirror-image forms", racemic),
        ("written inside a racemate mark (rac)", word == "rac" and (located or bare)),
        ("sign of optical rotation", label in ("+", "-")),
        ("does not say which of the two mirror-image forms is meant", relative),
        ("is a Fischer label", label in ("D", "L")),
        ("in the D series", label == "D"),
        ("in the L series", label == "L"),
        ("lie on the same side of the ring or double bond", label == "cis"),
        ("lie on opposite sides of the ring or double bond", label == "trans"),
        ("fixes the three-dimensional arrangement at one stereocentre", bare and word is None),
        ("the marks after it", label == "rel" and _marks_follow(trace, node)),
        ("at one stereocentre", label in ("R", "S", "R*", "S*")),
        ("at one double bond: its higher-ranked groups lie on opposite sides", label == "E"),
        ("at one double bond: its higher-ranked groups lie on the same side", label == "Z"),
        ("is a sugar configuration prefix", label.lower() in _SUGAR_PREFIXES),
        ("the stereocentres it covers", label.lower() != "glycero"),
        ("the stereocentre it covers is", label.lower() == "glycero"),
        ("is a stereo descriptor: part of how the name gives", True),
    ]
    made = [(phrase, fits) for phrase, fits in claims if phrase in line]
    for phrase, fits in made:
        if not fits:
            return True, f"{label}: '{phrase}' does not fit this mark"
    return bool(made), None


def _parent_problem(mol, nodes, node) -> tuple[bool, Optional[str]]:
    line = node["line"]
    cores = sum(1 for n in nodes if n["kind"] == "parent" and not _NOT_CORES.match(n["label"]))
    copies = max(node.get("copies") or 1, 1)
    seen, out = False, None
    if "the rest of the name is built around" in line:
        seen = True
        if cores > 1:
            out = f"the core of the rest, but the name has {cores} parent parts"
    m = re.search(r"one of the (\w+) cores this name is built from", line)
    if m:
        seen = True
        words = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
        said = words.get(m.group(1), int(m.group(1)) if m.group(1).isdigit() else -1)
        if said != cores:
            out = f"one of {m.group(1)} cores, the name has {cores}"
    need = (2 if "two fused benzene rings" in line else
            1 if ("benzene —" in line or "is a benzene ring." in line or "a benzene ring fused" in line) else 0)
    if need:
        seen = True
        owned = set(node["owns"])
        held = _benzene_rings(mol, owned)
        if held < need * copies:
            out = f"{need * copies} benzene ring(s), the part holds {held}"
    return seen, out


def _benzene_rings(mol, atoms) -> int:
    owned = set(atoms)
    return sum(1 for r in mol.GetRingInfo().AtomRings() if len(r) == 6 and set(r) <= owned
               and all(mol.GetAtomWithIdx(a).GetIsAromatic() and mol.GetAtomWithIdx(a).GetSymbol() == "C" for a in r))


def _phenyl_problem(mol, node) -> Optional[str]:
    """"a benzene ring attached by one of its carbons": an aromatic six-carbon ring per
    copy, bonded out of the part through a carbon."""
    owned = set(node["owns"])
    copies = max(node.get("copies") or 1, 1)
    if _benzene_rings(mol, owned) < copies:
        return "no benzene ring"
    out = [a for a in owned for n in mol.GetAtomWithIdx(a).GetNeighbors() if n.GetIdx() not in owned]
    if not out or any(mol.GetAtomWithIdx(a).GetSymbol() != "C" for a in out):
        return "not attached by a carbon"
    return None


def _functional_nh2_problem(mol, node) -> Optional[str]:
    """A functional-class word whose line names an -NH2 ("hydrazone", "semicarbazone"):
    one of its nitrogens carries two hydrogens."""
    if any(mol.GetAtomWithIdx(a).GetSymbol() == "N" and _h(mol, a) == 2 for a in node["owns"]):
        return None
    return "an NH2, no nitrogen carries two hydrogens"


def false_hover_lines(trace, nodes) -> list:
    """(label, line, why) for every hover line that says something false about the
    molecule on screen, or that uses a claim's vocabulary in a shape this check does not
    know."""
    mol = Chem.MolFromSmiles(trace.smiles)
    if mol is None:
        return []
    out = []
    for n in nodes:
        if any(a >= mol.GetNumAtoms() for a in n["owns"] + n["lights"]):
            continue                                  # an index problem is another class's
        known, why = False, None
        label = n["label"].strip("-").lower()
        if n["kind"] == "substituent" and label in _BARE_GROUP:
            known, why = True, _group_line_problem(mol, n, *_BARE_GROUP[label])
        elif n["kind"] == "suffix" and _AMINE_ENDING.match(label):
            known, why = True, _group_line_problem(mol, n, "N", "all", (2,))
        elif n["line"].startswith("Position ") and "hydrogen" in n["line"]:
            known, why = _h_locant_problem(mol, n)
        elif n["kind"] == "token" and n["label"].startswith("spiro["):
            known, why = _spiro_problem(mol, n)
        elif "names the anomer" in n["line"]:
            known, why = _anomer_problem(mol, n, nodes)
        elif n["kind"] == "stereo":
            known, why = _stereo_problem(trace, n)
        elif n["kind"] == "parent":
            known, why = _parent_problem(mol, nodes, n)
        elif n["kind"] == "token" and "isotope label" in n["line"]:
            known = True
            if "at the positions it names" in n["line"] and "-" not in n["label"].strip("()-"):
                why = "an isotope label with no locant names no position"
        elif n["kind"] == "hydro" and "records that hydrogens were added here" in n["line"]:
            known = True
        elif n["kind"] == "substituent" and "is a benzene ring attached by one of its carbons" in n["line"]:
            known, why = True, _phenyl_problem(mol, n)
        elif n["kind"] == "suffix" and "NH2 group in place of the carbonyl oxygen" in n["line"]:
            known, why = True, _functional_nh2_problem(mol, n)
        if why is not None:
            out.append((n["label"], n["line"], why))
        elif not known and _VOCAB.search(_QUOTED.sub("", n["line"])):
            out.append((n["label"], n["line"], "a claim this check does not recognise"))
        elif _unchecked_claim(n["line"]):
            out.append((n["label"], n["line"], "a claim beyond the one this check measured"))
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
    mol = Chem.MolFromSmiles(trace.smiles)
    centres, double = stereo_atoms(mol)
    for n in nodes:
        m = STEREO_MARK.match(n["label"]) if n["kind"] == "stereo" else None
        if not m or not n["lights"]:
            continue       # a mark that names no single atom lights nothing, by design
        pool = double if m.group(2) in ("E", "Z") else centres
        if len(n["lights"]) != 1 or any(
                m.group(1) not in trace.atoms[a].locants or a not in pool for a in n["lights"]):
            out.append("STEREO_WRONG_ATOM")
            break
    for n in nodes:
        if n["kind"] == "stereo" and BARE_DESCRIPTOR.match(n["label"]) and n["lights"]:
            pool = double if n["label"] in ("E", "Z") else centres
            if len(n["lights"]) != 1 or n["lights"][0] not in pool:
                out.append("STEREO_WRONG_ATOM")
                break
    if any(n["kind"] == "locant" and not n["lights"] and n["label"].lower() not in ("alpha", "beta")
           and not _unproven_component_number(trace, nodes, n) for n in nodes):
        out.append("LOCANT_UNLIT")
    if foreign_lights(trace, nodes, mol):
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
    if false_hover_lines(trace, nodes):
        out.append("HOVER_LINE_FALSE")
    return out or ["CLEAN"]


def run(names: list[str]) -> dict[str, list[str]]:

    results = {}
    for name in names:
        t = opsin_trace.trace(name)
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
                    "LINE_CLAIM_FALSE", "SUFFIX_OWNS_H", "OXIDATION_WRONG", "HOVER_LINE_FALSE"):
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
