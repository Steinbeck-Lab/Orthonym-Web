"""Trace -> the flat node list ExplainResponse v2 carries (spec §5).

Each written part (its copies share one key) becomes part nodes: a
substituent node, or a parent node plus a suffix node for a root. Token
ownership comes from app/token_owner.py (OPSIN's own placement, then written
neighbours). Every owned token that teaches something becomes a child: each
individual locant, each counting word, each hydro / indicated-hydrogen /
fusion / bridge / spiro token. Core tokens (group, suffix, unsaturator, ...)
ARE the part and get no child. A bracket's own locants and counting words
("2-[", "bis(") become top-level nodes that light the parts inside that
bracket -- or, for a multiplicative bracket ("4,4'-(...)di|phenol"), the
positions on the multiplied parents.

A functional-class word ("ketone", "ether", "anhydride", "oxime", "chloride") is a
part of its own, kind ``functional`` in the trace and a ``suffix`` node here, over the
atoms the word adds (app/opsin_trace.py takes them out of the alkyl written before
it); a word that adds none ("ester") owns none. Suffix and parent lines state what the
atoms are only when the atoms bear it out (app/glossary.py).

What a node lights is never a guess:

* a position locant lights the copy OPSIN put at that locant. When no copy
  sits there, the locant is read by structure, never by "any atom in the word
  that carries the number": on a multiplicative bridge ("4,4'-methylene|bis(...)",
  a substituent bonded to two copies of the root) it names the atoms of the
  multiplied root that the bridge is bonded to; otherwise it is the
  substituent's own attachment atom ("2-pyridyl"), its own ring heteroatom
  ("1,3-benzodioxol"), the atom of the parent the whole substituent chain is
  bonded to ("2-acetyloxy|benzoic acid"), or else an atom of its own part;
* a number written beside an element symbol in front of a substituent ("4-O-",
  "2,3,4-tri-O-acetyl") names the PARENT: the symbol lights the parent's atom of that
  element that the substituent chain is bonded to, the number the parent carbon that
  atom is bonded to -- never an atom of the substituent itself. When the bonds do not
  prove exactly one atom, nothing is lit;
* a counting word lights what the locants it counts light ("3,7-di|hydro"
  -> N3, N7; "2,6-di|one" -> both C=O);
* a stereo mark with a locant ("2S", "9Z", "17beta") lights the ONE atom
  that carries that locant AND is a stereocentre (R/S, alpha/beta) or sits
  on a stereo double bond (E/Z) in the traced molecule, searching the mark's
  scope's main part first and then the rest of its scope; if no single atom
  qualifies it lights nothing. Scope is IUPAC's: a set written in a bracket
  belongs to that bracket's main part (the part of the last token written
  directly in the bracket), a set outside every bracket to its word's root.
  A bare mark ("trans", "E") that does not start its word, and a Fischer
  D/L anywhere, belongs to the part written right after it
  ("L-alanyl-L-valyl-..."). OPSIN's own
  placement of stereo tokens is not used: it can leave a leading set parked
  in the first substituent, and the engine hoists a substituent's
  descriptor to the front of its names.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from rdkit import Chem

from .glossary import (
    describe_cage_multiplier, describe_functional, describe_locant, describe_part, describe_stereo,
    describe_token, suffix_claim_holds, token_line,
)
from .label_rules import (
    BARE_DESCRIPTOR, CONTEXTUAL, ELEMENT_LOCANT, GLUE, LOCANT_KINDS, NUMBER_LOCANT, STEREO_MARK,
    covered_positions, fusion_component_elements, indicated_h_items, label_span, locant_items,
    resolve_roles, root_spans, stereo_items,
)
from .opsin_trace import FUNCTIONAL_KIND, STEREO_KIND, Span, Trace, TracePart, WrittenToken
from .root_split import split_root
from .token_owner import (
    adopt_orphan_tokens, assign_owners, bracket_end, innermost_bracket, next_nonhyphen, tokens_of,
    written_brackets,
)

PART_NODE_KINDS = frozenset({"substituent", "parent", "suffix"})
_NODE_KIND = {
    "locant": "locant", "colonOrSemiColonDelimitedLocant": "locant", "spiroLocant": "locant",
    "multiplier": "multiplier", "ringAssemblyMultiplier": "multiplier",
    "hydro": "hydro", "indicatedHydrogen": "indicated_h", STEREO_KIND: "stereo",
}
_LINE_KINDS = frozenset({"multiplier", "ringAssemblyMultiplier", "hydro", "fusion", "vonBaeyer", "spiro",
                         "fusedRingBridge"})
_ADDED_H = re.compile(r"^(\d+[a-z]?'*)H$")
# Fischer D/L always prefix the part written right after them ("L-alanyl").
_FISCHER = frozenset({"D", "L", "DL"})
# A stereo set written "rel-(1R,2S)-" or "rac-(1R,2S)-": the word in front changes what
# every mark inside says (IUPAC P-93.1.2.1, P-93.1.3).
_SET_PREFIX = re.compile(r"^\s*(rel|rac)-?\(", re.IGNORECASE)


@dataclass
class _WrittenPart:
    kind: str
    key: Optional[Span]
    copies: list[TracePart]
    tokens: list[WrittenToken] = field(default_factory=list)


def _written_parts(trace: Trace) -> list[_WrittenPart]:
    grouped: dict = {}
    for part in trace.parts:
        key = (part.kind, part.span) if part.span is not None else (part.kind, None, part.index)
        grouped.setdefault(key, []).append(part)
    return [_WrittenPart(kind=k[0], key=k[1], copies=v) for k, v in grouped.items()]


def stereo_atoms(mol: Optional[Chem.Mol]) -> tuple[set, set]:
    """(stereocentres, atoms on a stereo double bond) of the traced molecule."""
    if mol is None:
        return set(), set()
    centres = {i for i, _ in Chem.FindMolChiralCenters(
        mol, includeUnassigned=True, useLegacyImplementation=False)}
    bonds = set()
    for bond in mol.GetBonds():
        if bond.GetStereo() != Chem.BondStereo.STEREONONE:
            bonds.update((bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()))
    return centres, bonds


def attachment_written_inside(trace: Trace, key: Optional[Span]) -> bool:
    """True when a substituent writes its own attachment point after its group
    ("pentan-3-yl", "pyridin-2-yl": the -3- / -2-), so a number in front can
    only be another's. Decided by WRITTEN ORDER: a locant token between the
    part's group token and its last own token. OPSIN leaves the attachment
    locant of a ring "-yl" unowned, so the owner cannot be asked."""
    mine = tokens_of(trace, key)
    core = next((t for t in mine if t.kind == "group"), None)
    if key is None or core is None:
        return False
    last = max(t.index for t in mine)
    return any(t.kind in LOCANT_KINDS and core.index < t.index < last for t in trace.tokens)


def _chain_end(trace: Trace, key: Optional[Span]) -> int:
    """Text position where the run of substituents written one after another
    from the part `key` ends ("acetyl|oxy|ethyl")."""
    subs = {p.span for p in trace.parts if p.kind == "substituent" and p.span is not None}
    end, seen = 0, set()
    while key is not None and key not in seen:
        seen.add(key)
        mine = tokens_of(trace, key)
        if not mine:
            break
        end = max(end, max(t.span[1] for t in mine))
        nxt = next_nonhyphen(trace.tokens, max(t.index for t in mine))
        key = nxt.owner if nxt is not None and nxt.kind == "group" and nxt.owner in subs else None
    return end


def chain_is_bracketed(trace: Trace, key: Optional[Span]) -> bool:
    """True when the part's leading locant and the whole run of substituents
    it starts ("(2-pyridylmethyl)", "(2-acetyloxyethyl)") sit inside one
    bracket pair. An unbracketed chain ("2-pyridyloxybenzoic acid") puts its
    leading locant on the parent (IUPAC P-16.5.1)."""
    core = next((t for t in tokens_of(trace, key) if t.kind == "group"), None)
    if core is None:
        return False
    # The locant run written directly in front of the group ("2-" in "2-pyridyl"):
    # its tokens belong to no part (owner None), so walk back from the group.
    # "cyclo" / "tert-" are the substituent's own name ("4-cyclopropylmethoxy"):
    # the locant is written before them.
    lead, j = None, core.index - 1
    while j >= 0 and trace.tokens[j].kind in LOCANT_KINDS | {"hyphen", "cyclo", "alkaneStemModifier", "heteroatom"}:
        if trace.tokens[j].kind in LOCANT_KINDS:
            lead = trace.tokens[j]
        j -= 1
    if lead is None:
        return False
    end, stack = _chain_end(trace, key), []
    for pos, ch in enumerate(trace.text):
        if ch in "([{":
            stack.append(pos)
        elif ch in ")]}" and stack:
            if stack.pop() < lead.span[0] and pos >= end:
                return True
    return False


def joined_to_next_substituent(trace: Trace, key: Optional[Span]) -> bool:
    """True when a substituent is followed directly (hyphens skipped) by
    another substituent's group token it is joined to ("acetyl|oxy",
    "pyridyl|methyl")."""
    mine = tokens_of(trace, key)
    if key is None or not mine:
        return False
    nxt = next_nonhyphen(trace.tokens, max(t.index for t in mine))
    return (nxt is not None and nxt.kind == "group" and nxt.owner not in (None, key)
            and any(p.span == nxt.owner and p.kind == "substituent" for p in trace.parts))


def pair_line(role: str, element: str, loc: str, lit) -> str:
    """The line of half of a "4-O-" pair: what it lit, or the plain position when it
    lit nothing."""
    if not lit:
        return describe_locant("substituent", loc)
    return describe_locant("oxy_element", loc) if role == "element" else describe_locant("oxy_number", loc, element)


class _Builder:
    def __init__(self, trace: Trace, parts: list[_WrittenPart]):
        self.t = trace
        self.parts = parts
        self.nodes: list[dict] = []
        self.covered = covered_positions(trace.tokens)
        self.by_index = {a.index: a for a in trace.atoms}
        self.part_node: dict[Span, tuple[str, list[int]]] = {}   # key -> (node id, atoms)
        self.suffix_node: dict[Span, tuple[str, list[int], dict]] = {}  # root key -> (id, atoms, locants)
        self.mol = Chem.MolFromSmiles(trace.smiles)
        self.centres, self.double = stereo_atoms(self.mol)
        self.rings = [frozenset(r) for r in self.mol.GetRingInfo().AtomRings()] if self.mol is not None else []
        self.ring_atoms = frozenset(a for r in self.rings for a in r)
        self.by_key = {w.key: w for w in parts if w.key is not None}
        self.part_of = {a: p for p in trace.parts for a in p.atoms}
        self.carbohydrate_atoms: Optional[list[int]] = None   # set while a sugar root's children are built

    def add(self, kind, label, span, *, line, parent=None, owns=(), lights=(), copies=1) -> str:
        node_id = f"n{len(self.nodes)}"
        self.nodes.append({
            "id": node_id, "parent": parent, "kind": kind, "label": label,
            "span": [span[0], span[1]] if span else None, "copies": copies,
            "owns": sorted(set(owns)), "lights": sorted(set(lights)),
            "atoms_unmapped": False, "line": line,
        })
        return node_id

    def text(self, span: Span) -> str:
        return self.t.text[span[0]:span[1]]

    def trim(self, span: Span) -> Span:
        a, b = span
        while b > a and self.t.text[b - 1] in "-,":
            b -= 1
        return (a, b)

    def with_locant(self, atoms, locant) -> list[int]:
        return [i for i in atoms if locant in self.by_index[i].locants]

    def modifier(self, atoms, at: Optional[str], written: str) -> tuple[list[int], str]:
        """(atoms, line) of a hydro / indicated-hydrogen locant: `at` is the locant as
        OPSIN numbers it (None when it names no atom), `written` the text to show then."""
        hit = self.with_locant(atoms, at) if at is not None else []
        element = self.by_index[hit[0]].element if len(hit) == 1 else None
        return hit, describe_locant("modifier", at or written, element, mol=self.mol,
                                    atom=hit[0] if len(hit) == 1 else None)

    def component_atom(self, elements: list, k: Optional[int], atoms) -> list[int]:
        """The ONE atom of `atoms` that the k-th number of a fusion component names,
        when it is proven, else []. Proven means: the atoms of that element in the
        fused system are exactly as many as the component puts there (so any of them
        is the component's, and with one it is THE atom), or, among several, exactly
        one shares a ring with an atom proven by the first rule. Which of several
        equal heteroatoms a number names is not provable, so it lights nothing."""
        if k is None or elements[k] is None or self.mol is None:
            return []
        pool = [a for a in atoms if a < self.mol.GetNumAtoms()]
        by_element = lambda e: [a for a in pool if self.by_index[a].element == e]
        sole = {e: by_element(e)[0] for e in set(elements)
                if e is not None and elements.count(e) == 1 and len(by_element(e)) == 1}
        if elements[k] in sole:
            return [sole[elements[k]]]
        if elements.count(elements[k]) != 1:
            return []
        near = [a for a in by_element(elements[k])
                if sole and all(any({a, s} <= r for r in self.rings) for s in sole.values())]
        return near if len(near) == 1 else []

    def spiro_lookup(self, tokens, i: int, atoms, loc: str) -> Optional[str]:
        """The locant as OPSIN numbers it, or None when it names no atom. In
        spiro[A-x,y'-B] every locant written INSIDE the brackets after the
        spiro locants belongs to a later component, and OPSIN primes those
        atoms ("6-oxa" in the second component is 6'): the bare number would
        light the first component's atom. A locant written after the closing
        bracket ("spiro[...]-1(2H)-yl", "-1-ium") is the whole part's own and
        stays as written. A primed number no atom carries lights nothing."""
        if loc.endswith("'") or tokens[i].kind == "spiroLocant":
            return loc
        pos = tokens[i].span[0]
        primes = 0
        for head in (t for t in tokens[:i] if t.kind == "polyCyclicSpiro"):
            end = bracket_end(self.t.text, head.span[1])
            if end is not None and pos < end:
                primes = sum(1 for t in tokens[:i] if t.kind == "spiroLocant"
                             and head.span[1] <= t.span[0] and t.span[1] <= pos)
        if not primes:
            return loc
        primed = loc + "'" * primes
        return primed if self.with_locant(atoms, primed) else None

    def word(self, pos: int) -> int:
        return self.t.text.count(" ", 0, pos)

    def atoms_of(self, w: _WrittenPart) -> list[int]:
        return [a for c in w.copies for a in c.atoms]

    # -- parts ------------------------------------------------------------
    def unplaced_part(self, w: _WrittenPart) -> None:
        """A part OPSIN gave no key: still owns its atoms, listed as not
        placed in the name. Never raises."""
        owns = self.atoms_of(w)
        kind = "substituent" if w.kind == "substituent" else "parent"
        self.add(kind, w.kind, None, owns=owns, lights=owns, copies=len(w.copies),
                 line=describe_part(kind, w.kind, len(set(owns)), copies=len(w.copies)))

    def foreign_replacement_locants(self, w: _WrittenPart, roles: list[str]) -> list[str]:
        """A locant written right before a heteroatom or alkane-stem token reads
        as part of the name ("1,3-|dioxolanyl", "4-|oxa-1-aza..."). It is a
        POSITION, in front of the substituent, when either
          * OPSIN itself placed the part at that number (TracePart.locant:
            "1-oxiranylpropan-2-one", "N-hexadecylnaphthalen-1-amine" -- the
            number is the parent's position the whole substituent hangs on), or
          * the token is a heteroatom and none of the part's heteroatoms carries
            the number ("3-oxiranylmethoxy": oxirane's oxygen is O1)."""
        own_hetero = [self.by_index[a] for a in self.atoms_of(w) if self.by_index[a].element != "C"]
        placed = {c.locant for c in w.copies if c.locant}
        out = list(roles)
        for i, tok in enumerate(w.tokens):
            if tok.kind not in LOCANT_KINDS or roles[i] != "core":
                continue
            after = next((t for t in w.tokens[i + 1:] if t.kind not in CONTEXTUAL and t.kind not in GLUE), None)
            if after is None or after.kind not in ("heteroatom", "alkaneStemComponent"):
                continue
            items = [loc for loc, _ in locant_items(self.t.text, tok.span)]
            if placed & set(items):
                out[i] = "prefix"
            elif after.kind == "heteroatom" and not any(
                    loc in atom.locants for loc in items for atom in own_hetero):
                out[i] = "prefix"
        return out

    def substituent(self, w: _WrittenPart) -> None:
        roles = self.foreign_replacement_locants(w, resolve_roles(w.tokens, "substituent", len(w.copies)))
        span = label_span(self.t.text, w.tokens, roles, self.covered, w.key)
        label = self.text(span)
        owns = self.atoms_of(w)
        node = self.add("substituent", label, span, owns=owns, lights=owns, copies=len(w.copies),
                        line=describe_part("substituent", label, len(set(owns)), copies=len(w.copies),
                                           mol=self.mol, atoms=owns))
        self.part_node[w.key] = (node, owns)
        # A glycosyl substituent ("alpha-D-mannopyranosyl|oxy") names its anomer
        # the same way a sugar root does.
        self.carbohydrate_atoms = owns if any(t.kind == "carbohydrateRingSize" for t in w.tokens) else None
        self.children(node, w, w.tokens, roles, owns, owns, mode="substituent")
        self.carbohydrate_atoms = None

    def root(self, w: _WrittenPart) -> None:
        roles = resolve_roles(w.tokens, "root", len(w.copies))
        spans = root_spans(self.t.text, w.tokens, roles, self.covered, w.key)
        parent_atoms: list[int] = []
        suffix_atoms: list[int] = []
        suffix_locants: dict[int, str] = {}
        for c in w.copies:
            split = split_root(self.t, c.atoms, self.mol)
            parent_atoms += split.parent_atoms
            suffix_atoms += split.suffix_atoms
            suffix_locants.update(split.suffix_locants)
        # A pyranose/furanose names ring and every O together, and OPSIN's
        # locants do not tell the ring O from the OH groups ("O'", "O''"...),
        # so a carbohydrate root is never split into parent + suffix.
        carbohydrate = any(t.kind == "carbohydrateRingSize" for t in w.tokens)
        has_suffix = spans.suffix is not None and bool(suffix_atoms) and not carbohydrate
        if not has_suffix:
            # Retained names (phenol) name ring and OH in one token: the atoms
            # stay with the parent that actually names them.
            parent_atoms += suffix_atoms
            suffix_atoms = []
        parent_span = spans.parent if has_suffix or spans.suffix is None else (spans.parent[0], spans.suffix[1])
        label = self.text(parent_span)
        parent = self.add("parent", label, parent_span, owns=parent_atoms, lights=parent_atoms,
                          copies=len(w.copies),
                          line=describe_part("parent", label, len(set(parent_atoms)), copies=len(w.copies)))
        self.part_node[w.key] = (parent, parent_atoms + suffix_atoms)
        run = spans.suffix_tokens if has_suffix else frozenset()
        head = [(t, r) for t, r in zip(w.tokens, roles) if t.index not in run]
        self.carbohydrate_atoms = parent_atoms if carbohydrate else None
        self.children(parent, w, [t for t, _ in head], [r for _, r in head], parent_atoms, parent_atoms,
                      mode="parent")
        self.carbohydrate_atoms = None
        if has_suffix:
            s_label = self.text(spans.suffix_label)
            carrying = set(suffix_locants.values())
            lights = suffix_atoms + [i for i in parent_atoms if carrying & set(self.by_index[i].locants)]
            suffix = self.add("suffix", s_label, spans.suffix, owns=suffix_atoms, lights=lights,
                              line=describe_part("suffix", s_label, len(set(suffix_atoms)),
                                                 holds=suffix_claim_holds(s_label, self.mol, suffix_atoms),
                                                 mol=self.mol, atoms=suffix_atoms))
            self.suffix_node[w.key] = (suffix, suffix_atoms, suffix_locants)
            tail = [(t, r) for t, r in zip(w.tokens, roles) if t.index in run]
            self.children(suffix, w, [t for t, _ in tail], [r for _, r in tail], parent_atoms, lights,
                          mode="suffix", suffix_atoms=suffix_atoms, suffix_locants=suffix_locants)

    def functional(self, w: _WrittenPart) -> None:
        """A functional-class word ("ketone", "ether", "anhydride", "oxime"): its own
        node, over its own atoms (the trace took them out of the alkyls written
        before it). A word that adds no atoms ("ester") owns none."""
        atoms = self.atoms_of(w)
        span = (min(t.span[0] for t in w.tokens), max(t.span[1] for t in w.tokens))
        label = self.text(span)
        node = self.add("suffix", label, span, owns=atoms, lights=atoms,
                        line=describe_functional(label, len(set(atoms))))
        self.part_node[w.key] = (node, atoms)

    # -- children ---------------------------------------------------------
    def children(self, owner, w, tokens, roles, atoms, token_lights, *, mode,
                 suffix_atoms=(), suffix_locants=None) -> None:
        """`atoms` are where locants are looked up (the parent skeleton for a
        root's suffix); `token_lights` is what a token child lights when no
        locant it counts says better."""
        first_core = next((i for i, r in enumerate(roles) if r == "core"), len(roles))
        used_copies: set[int] = set()
        counted: set[int] = set()        # what the latest locant run lights
        for i, tok in enumerate(tokens):
            if roles[i] == "glue":
                continue
            if tok.kind in LOCANT_KINDS:
                target = next((tokens[j] for j in range(i + 1, len(tokens))
                               if roles[j] != "glue" and tokens[j].kind not in CONTEXTUAL), None)
                items = locant_items(self.t.text, tok.span)
                written = {loc: sum(1 for x, _ in items if x == loc) for loc, _ in items}
                counted = set()
                for item_at, (loc, sub) in enumerate(items):
                    added = _ADDED_H.match(loc)
                    if added:
                        # "2(1H)": hydrogen added at position 1 of the parent.
                        hit, line = self.modifier(atoms, self.spiro_lookup(tokens, i, atoms, added.group(1)),
                                                  added.group(1))
                        self.add("indicated_h", loc, sub, parent=owner, lights=hit, line=line)
                        continue
                    component = (None if any(t.kind == "polyCyclicSpiro" for t in tokens)
                                 else fusion_component_elements(tokens, i, self.t.text))
                    if component is not None:
                        # A number of a fusion component's own numbering ("[1,3]thiazolo"):
                        # the fused system's atoms carry other numbers, so light only
                        # what the element and the rings prove, else nothing.
                        k = [x for x, _ in items].index(loc) if len(items) == len(component) else None
                        lit = self.component_atom(component, k, atoms)
                        counted.update(lit)
                        self.add("locant", loc, sub, parent=owner, lights=lit,
                                 line=describe_locant("position", loc))
                        continue
                    pair = (self.oxy_pair(tokens, i, items, item_at, set(self.atoms_of(w)))
                            if mode == "substituent" and i < first_core else None)
                    if pair is not None:
                        # "4-O-": the O names the PARENT's oxygen of that element, the number
                        # the parent carbon it is bonded to -- never the substituent's own atoms.
                        role, element, lit = pair
                        self.add("locant", loc, sub, parent=owner, lights=lit, line=pair_line(role, element, loc, lit))
                        continue
                    at = self.spiro_lookup(tokens, i, atoms, loc)
                    if at is None:
                        self.add("locant", loc, sub, parent=owner, lights=[],
                                 line=describe_locant("position", loc))
                        continue
                    lights, line = self.locant(at, i < first_core,
                                               target, mode, atoms,
                                               used_copies, suffix_atoms, suffix_locants or {},
                                               written[loc], w, [x for x, _ in items])
                    counted.update(lights)
                    self.add("locant", loc, sub, parent=owner, lights=lights, line=line)
                if tok.kind == "spiroLocant":
                    # The spiro locants name the shared atom, not what the next
                    # component's counting words and ring tokens refer to: those
                    # light the skeleton, as the first component's do.
                    counted = set()
            elif tok.kind == "indicatedHydrogen":
                for loc, sub in indicated_h_items(self.t.text, tok.span):
                    hit, line = self.modifier(atoms, self.spiro_lookup(tokens, i, atoms, loc), loc)
                    self.add("indicated_h", self.text(sub), sub, parent=owner, lights=hit, line=line)
            elif tok.kind == "isotopeSpecification":
                # "(2H3)", "(125I)": it lights the atoms of the isotope's element in
                # the part, and nothing when it names no element it can read.
                span = self.trim(tok.span)
                symbols = set(re.findall(r"\d+([A-Z][a-z]?)", self.text(span)))
                self.add("token", self.text(span), span, parent=owner,
                         lights=[a for a in token_lights if self.by_index[a].element in symbols],
                         line=describe_token(tok.kind, self.text(span)))
            elif tok.kind in _LINE_KINDS:
                span = self.trim(tok.span)
                line = describe_token(tok.kind, self.text(span))
                if tok.kind == "multiplier" and self.counts_cage_rings(tokens, roles, i):
                    line = describe_cage_multiplier(self.text(span))
                self.add(_NODE_KIND.get(tok.kind, "token"), self.text(span), span, parent=owner,
                         lights=counted or token_lights, line=line)
            elif roles[i] == "prefix":
                span = self.trim(tok.span)
                self.add(_NODE_KIND.get(tok.kind, "token"), self.text(span), span, parent=owner,
                         lights=token_lights, line=token_line(tok.kind, self.text(span)))
            elif roles[i] == "core":
                counted = set()

    @staticmethod
    def counts_cage_rings(tokens, roles, i: int) -> bool:
        """"bi" / "tri" in "bicyclo[2.2.2]octane" count the rings of the cage: OPSIN's
        von Baeyer token ("cyclo[2.2.2]") follows. ("di" in "dicyclohexyl" counts copies:
        a plain cyclo token follows.)"""
        rest = next((t for j, t in enumerate(tokens[i + 1:], i + 1) if roles[j] != "glue" and t.kind != "hyphen"), None)
        return rest is not None and rest.kind == "vonBaeyer"

    # -- structure helpers (bonds of the traced molecule) --------------------
    def nbrs(self, atom: int) -> list[int]:
        if self.mol is None or atom >= self.mol.GetNumAtoms():
            return []
        return [n.GetIdx() for n in self.mol.GetAtomWithIdx(atom).GetNeighbors()]

    def implicit_attachment(self, own, atom: int, loc: str) -> bool:
        """A carbocyclic monocycle attached at its position 1 (phenyl,
        cyclohexyl) never writes that number: the `1` in front is not its."""
        if loc != "1" or self.mol is None:
            return False
        if any(self.by_index[a].element != "C" for a in own):
            return False
        own = set(own)
        return len([r for r in self.rings if r <= own]) == 1

    def linker_atom(self, atom: int) -> bool:
        part = self.part_of.get(atom)
        return (part is not None and part.kind == "substituent"
                and any(ELEMENT_LOCANT.match(loc) for loc in self.by_index[atom].locants))

    def in_ring(self, atom: int) -> bool:
        return atom in self.ring_atoms

    def component(self, start) -> set[int]:
        """`start` plus every substituent atom bonded to it, transitively: the
        whole substituent chain/tree one root position carries."""
        comp, stack = set(start), list(start)
        while stack:
            for n in self.nbrs(stack.pop()):
                part = self.part_of.get(n)
                if n not in comp and part is not None and part.kind == "substituent":
                    comp.add(n)
                    stack.append(n)
        return comp

    def edge(self, comp) -> set[int]:
        return {n for a in comp for n in self.nbrs(a) if n not in comp}

    def carrying(self, atoms, loc) -> list[int]:
        return sorted(a for a in atoms if loc in self.by_index[a].locants)

    def root_edge(self, inside) -> tuple[set[int], bool]:
        """(root atoms bonded to `inside`, whether `inside` is a bridge: it is
        bonded to two or more distinct copies of a multiplied root)."""
        roots = {a for a in self.edge(inside) if self.part_of.get(a) is not None
                 and self.part_of[a].kind == "root"}
        return roots, len({self.part_of[a].index for a in roots}) >= 2

    def anomeric_carbon(self, atoms, *, attached: bool = False) -> list[int]:
        """The ring carbon of a sugar that holds both a ring oxygen and an
        exocyclic oxygen, when exactly one does; else nothing. A glycosyl
        substituent (`attached`) holds its exocyclic bond to whatever it is
        attached to, which lies outside its own atoms."""
        if self.mol is None:
            return []
        pool, found = set(atoms), []
        for a in sorted(pool):
            atom = self.mol.GetAtomWithIdx(a)
            if atom.GetSymbol() != "C" or not atom.IsInRing():
                continue
            ring_o = exo_o = False
            for n in atom.GetNeighbors():
                in_ring = self.mol.GetBondBetweenAtoms(a, n.GetIdx()).IsInRing()
                if n.GetSymbol() == "O" and n.GetIdx() in pool:
                    if in_ring:
                        ring_o = True
                    else:
                        exo_o = True
                elif attached and n.GetIdx() not in pool and not in_ring:
                    exo_o = True
            if ring_o and exo_o:
                found.append(a)
        return found if len(found) == 1 else []

    def oxy_pair(self, tokens, i: int, items, k: int, own: set[int]):
        """(role, element, atoms) when item k of locant token i is half of a "4-O-" pair,
        else None. "4-O-beta-D-galactopyranosyl-D-glucopyranose", "6-O-acetyl",
        "2,3,4-tri-O-acetyl", "6-O-(alpha-L-rhamnopyranosyl)": a number and an element
        symbol written one after the other in front of a substituent say the substituent
        is joined through the PARENT's atom of that element, on the parent carbon with
        that number. So the number lights that parent carbon and the symbol that parent
        atom -- both found by the bonds of the substituent chain (`own` is its atoms),
        outside the substituent's own atoms -- and when the bonds do not prove exactly
        one, nothing is lit. role is "number" or "element"."""
        text = self.t.text
        number = lambda x: bool(NUMBER_LOCANT.match(x))
        element = lambda x: bool(ELEMENT_LOCANT.match(x))
        loc, (a, b) = items[k][0], items[k][1]
        found = None
        if element(loc) and k > 0 and number(items[k - 1][0]) and text[items[k - 1][1][1]:a] == "-":
            found = ("element", loc, [items[k - 1][0]])
        elif number(loc) and k + 1 < len(items) and element(items[k + 1][0]) \
                and text[b:items[k + 1][1][0]] == "-":
            found = ("number", items[k + 1][0], [loc])
        else:
            def run_past(j: int, step: int):
                j += step
                while 0 <= j < len(tokens) and tokens[j].kind in ("hyphen", "multiplier"):
                    j += step
                return j if 0 <= j < len(tokens) else None
            if element(loc) and len(items) == 1:
                j = run_past(i, -1)
                if j is not None and tokens[j].kind in LOCANT_KINDS:
                    numbers = [x for x, _ in locant_items(text, tokens[j].span)]
                    if numbers and all(number(x) for x in numbers):
                        found = ("element", loc, numbers)
            elif number(loc):
                j = run_past(i, 1)
                if j is not None and tokens[j].kind in LOCANT_KINDS:
                    nxt = locant_items(text, tokens[j].span)
                    if len(nxt) == 1 and element(nxt[0][0]) and all(number(x) for x, _ in items):
                        found = ("number", nxt[0][0], [loc])
        if found is None:
            return None
        role, symbol, numbers = found
        comp = self.component(own)
        joined = [y for y in self.edge(comp) if self.by_index[y].element == symbol.rstrip("'")]
        carbon: dict[str, set[int]] = {}
        joint: dict[str, set[int]] = {}
        for y in joined:
            for x in self.nbrs(y):
                if x in comp:
                    continue
                for n in numbers:
                    if n in self.by_index[x].locants:
                        carbon.setdefault(n, set()).add(x)
                        joint.setdefault(n, set()).add(y)
        unique = [n for n in numbers if len(carbon.get(n, ())) == 1]
        if role == "number":
            lit = sorted(carbon[loc]) if loc in unique else []
        else:
            lit = sorted(y for n in unique for y in joint[n])
        return role, symbol, lit

    def leading_substituent_locant(self, loc, token_locs, w) -> list[int]:
        """A substituent's leading locant that no copy of it carries. Decided
        by the bonds, in this order:
          1. bridge: the substituent chain is bonded to two copies of a
             multiplied root ("4,4'-methylene|bis(...)") and the token is not
             its own ring locants ("1,4-phenylene"): the root atoms it bonds to;
          2. its own attachment atom ("2-pyridyl", "1-naphthyl": the atom that
             carries the locant AND is bonded out of the substituent) -- unless
             the substituent writes its attachment inside itself
             ("3-pentan-3-yloxy|cyclohexene": the 3 in front is the
             cyclohexene's); when it is merely joined to a following
             substituent ("2-acetyloxy", "2-pyridyl|methyl") only a RING atom
             counts: an open-chain attachment carbon is the parent's position;
          3. its own ring heteroatom ("1,3-benzodioxol", "1-benzofuran");
          4. the atom of the parent the whole chain is bonded to
             ("2-acetyloxy|benzoic acid");
          5. any own atom carrying the locant, else the whole part."""
        own = set(self.atoms_of(w))
        comp = self.component(own)
        roots, bridge = self.root_edge(comp)
        if bridge and not all(self.carrying(own, x) for x in token_locs):
            hit = self.carrying(roots, loc)
            if hit:
                return hit
        inside = attachment_written_inside(self.t, w.key)
        if joined_to_next_substituent(self.t, w.key) and not chain_is_bracketed(self.t, w.key):
            # An unbracketed chain ("2-pyridyloxybenzoic acid", "1-phenylmethoxynaphthalene"):
            # the number in front names the parent position the whole chain hangs on.
            hit = self.carrying(self.edge(comp), loc)
            if hit:
                return hit
        if not inside:
            attach = [a for a in self.carrying(own, loc) if any(n not in own for n in self.nbrs(a))]
            # Joined to a following substituent ("2-acetyloxy", "2-propan-2-yloxy"):
            # an open-chain atom carrying the number is the parent's position,
            # but a ring atom is the ring substituent's own attachment point
            # ("2-pyridyl|methyl", "2-naphthyl|oxy").
            if joined_to_next_substituent(self.t, w.key):
                # (a bracketed chain only: an unbracketed one returned above)
                attach = [a for a in attach if self.in_ring(a) and not self.implicit_attachment(own, a, loc)]
            if attach:
                return attach
        if ELEMENT_LOCANT.match(loc) and joined_to_next_substituent(self.t, w.key):
            # "N-|diaminomethylidenecarbamimidoyl": an element-symbol number in
            # front of a chain names the atom of a LATER chain member, never this
            # substituent's own same-lettered atom (amino's N).
            hit = self.chain_edge(w, loc)
            if hit:
                return hit
        hetero = [a for a in self.carrying(own, loc) if self.by_index[a].element != "C"]
        if hetero:
            return hetero
        return (self.chain_edge(w, loc) or self.carrying(self.edge(comp), loc)
                or self.carrying(own, loc) or sorted(own))

    def chain_edge(self, w, loc) -> list[int]:
        """Walk the substituents written one after another from `w`
        ("acetyl|oxy|ethyl"): the first prefix of that chain that is bonded to
        an atom carrying `loc` names it. "4-(2-acetyloxyethyl)phenol": acetyl
        alone is bonded to the O, acetyl+oxy to ethyl C2."""
        seen, atoms, part = {w.key}, set(self.atoms_of(w)), w
        while True:
            edge = self.edge(atoms)
            # A linker carbon (methyl, methoxy's CH2) carries its number beside
            # an element symbol ("1/C"): that is not a position the chain hangs on.
            # (unless the number IS an element symbol: "N-ethylcarbamoyl" names that N)
            element = bool(ELEMENT_LOCANT.match(loc))
            hit = [a for a in self.carrying(edge, loc) if element or not self.linker_atom(a)]
            if hit:
                return hit
            last = max(t.index for t in part.tokens) if part.tokens else -1
            nxt = next_nonhyphen(self.t.tokens, last)
            part = self.by_key.get(nxt.owner) if nxt is not None and nxt.kind == "group" else None
            if part is None or part.kind != "substituent" or part.key in seen:
                return []
            seen.add(part.key)
            atoms |= set(self.atoms_of(part))

    def locant(self, loc, leading, target, mode, atoms, used, suffix_atoms, suffix_locants,
               written, w, token_locs):
        if target is not None and target.kind == "hydro":
            return self.modifier(atoms, loc, loc)
        if (mode == "substituent" and self.carbohydrate_atoms is not None
                and loc.lower() in ("alpha", "beta")):
            lit = self.anomeric_carbon(self.carbohydrate_atoms, attached=True)
            return lit, describe_locant("position", loc, anomer=True, mol=self.mol, atom=lit[0] if lit else None)
        if mode == "substituent" and leading:
            at_loc = [c for c in w.copies if c.locant == loc]
            if len(at_loc) > written:
                # Written once for several copies ("bis(4-chlorophenyl)"): the
                # locant names all of them.
                return [a for c in at_loc for a in c.atoms], describe_locant("substituent", loc)
            for c in at_loc:
                if c.index not in used:
                    used.add(c.index)
                    return list(c.atoms), describe_locant("substituent", loc)
            if at_loc:
                return [a for c in at_loc for a in c.atoms], describe_locant("substituent", loc)
            return self.leading_substituent_locant(loc, token_locs, w), describe_locant("substituent", loc)
        if mode == "suffix":
            own = [i for i in suffix_atoms if suffix_locants.get(i) == loc]
            return own + self.with_locant(atoms, loc), describe_locant("suffix", loc)
        hit = self.with_locant(atoms, loc)
        if not hit and self.carbohydrate_atoms is not None and loc.lower() in ("alpha", "beta"):
            # A sugar's anomer mark names the anomeric carbon -- only when the
            # structure proves exactly one; otherwise it lights nothing.
            lit = self.anomeric_carbon(self.carbohydrate_atoms)
            return lit, describe_locant("position", loc, anomer=True, mol=self.mol, atom=lit[0] if lit else None)
        return (hit or list(atoms)), describe_locant("position", loc)

    # -- brackets, orphans, stereo ----------------------------------------
    def bracket_token(self, tok: WrittenToken, bracket: Span) -> None:
        """A bracket's own locant / counting word lights every part whose
        first written token sits inside that bracket -- or, when the bracket
        is bonded to two copies of a multiplied root
        ("4,4'-(propane-2,2-diyl)di|phenol"), the positions it names on those
        roots."""
        inside = [w for w in self.parts if w.tokens and bracket[0] < w.tokens[0].span[0] < bracket[1]]
        atoms = [a for w in inside for a in self.atoms_of(w)]
        if tok.kind in LOCANT_KINDS:
            roots, bridge = self.root_edge(self.component(atoms)) if atoms else (set(), False)
            items = locant_items(self.t.text, tok.span)
            for k, (loc, sub) in enumerate(items):
                pair = self.oxy_pair(self.t.tokens, tok.index, items, k, set(atoms)) if atoms else None
                if pair is not None:
                    role, element, lit = pair
                    self.add("locant", loc, sub, lights=lit, line=pair_line(role, element, loc, lit))
                    continue
                lights = atoms
                if bridge:
                    lights = self.carrying(roots, loc) or atoms
                self.add("locant", loc, sub, lights=lights, line=describe_locant("substituent", loc))
            return
        span = self.trim(tok.span)
        label = self.text(span)
        self.add(_NODE_KIND.get(tok.kind, "token"), label, span, lights=atoms, line=token_line(tok.kind, label))

    def orphan(self, tok: WrittenToken) -> None:
        span = self.trim(tok.span)
        label = self.text(span)
        self.add(_NODE_KIND.get(tok.kind, "token"), label, span,
                 line=token_line(tok.kind, label))

    def stereo_atom(self, locant: str, descriptor: str, scope_parts: list[_WrittenPart],
                    head: Optional[_WrittenPart]):
        """(part key, atom) of the ONE atom a mark names, or (None, None)."""
        pool = self.double if descriptor in ("E", "Z") else self.centres
        order = ([head] if head else []) + [w for w in scope_parts if w is not head]
        for group in ([order[0]] if order else [], order):
            hits = [(w.key, a) for w in group for a in self.atoms_of(w)
                    if a in pool and locant in self.by_index[a].locants]
            atoms = {a for _, a in hits}
            if len(atoms) == 1:
                return hits[0]
            if len(atoms) > 1 and descriptor in ("E", "Z"):
                keys = {k for k, _ in hits}
                if len(keys) == 1:                 # both ends of one double bond
                    return hits[0][0], sorted(atoms)[0]
        return None, None

    def stereo(self, owners: dict) -> None:
        tokens = self.t.tokens
        brackets = written_brackets(tokens)
        by_key = self.by_key
        for idx, tok in enumerate(tokens):
            if tok.kind != STEREO_KIND:
                continue
            scope = innermost_bracket(brackets, tok.span[0])
            if scope is not None:
                scope_parts = [w for w in self.parts if w.tokens and w.kind != FUNCTIONAL_KIND and
                               scope[0] < w.tokens[0].span[0] < scope[1]]
                direct = [t for t in tokens if t.owner is not None and
                          innermost_bracket(brackets, t.span[0]) == scope]
                head = by_key.get(direct[-1].owner) if direct else None
            else:
                word = self.word(tok.span[0])
                scope_parts = [w for w in self.parts if w.tokens and w.kind != FUNCTIONAL_KIND
                               and self.word(w.tokens[0].span[0]) == word]
                roots = [w for w in scope_parts if w.kind == "root"]
                head = roots[0] if roots else (scope_parts[-1] if scope_parts else None)
            leading = not any(p.kind not in GLUE and p.kind != STEREO_KIND
                              and self.word(p.span[0]) == self.word(tok.span[0]) for p in tokens[:idx])
            written = next((t for t in tokens[idx + 1:] if owners.get(t.index) is not None), None)
            bridge = None
            if written is not None and written.kind == "fusedRingBridge":
                bridge = next((n for n in self.nodes if n["kind"] == "token"
                               and n["span"] == list(self.trim(written.span))), None)
            first_new = len(self.nodes)
            written_set = _SET_PREFIX.match(self.t.text[tok.span[0]:tok.span[1]])
            within = written_set.group(1).lower() if written_set else None
            for label, span in stereo_items(self.t.text, tok.span):
                m = STEREO_MARK.match(label)
                if m:
                    key, atom = self.stereo_atom(m.group(1), m.group(2).rstrip("*"), scope_parts, head)
                    owner_key = key if key is not None else (head.key if head else None)
                    parent = self.part_node.get(owner_key, (None, []))[0]
                    self.add("stereo", label, span, parent=parent,
                             lights=[atom] if atom is not None else [],
                             line=describe_stereo(label, within))
                elif BARE_DESCRIPTOR.match(label) and head is not None:
                    # No locant: light the stereocentre (or stereo double
                    # bond) of the scope's main part only if it has exactly one.
                    pool = self.double if label in ("E", "Z") else self.centres
                    hits = sorted(a for a in self.atoms_of(head) if a in pool)
                    single = hits[:1] if (len(hits) == 1 or (label in ("E", "Z") and len(hits) == 2)) else []
                    self.add("stereo", label, span, parent=self.part_node.get(head.key, (None, []))[0],
                             lights=single, line=describe_stereo(label, within))
                elif NUMBER_LOCANT.match(label):
                    # A locant listed with a mark: "3,17beta-diol" (it is the
                    # suffix's own locant) or "11beta,17,21-trihydroxy" (it is
                    # the substituent's). What the list precedes decides.
                    after = next((t for t in tokens[idx + 1:] if owners.get(t.index) is not None), None)
                    nxt = None
                    if after is not None and owners[after.index].kind == "part":
                        nxt = by_key.get(owners[after.index].span)
                    self.token_locant(label, span, head, nxt, bridge)
                else:
                    # A bare mark (L, D, trans, E) names no atom. D/L, and any
                    # mark that does not start its word, describe the part
                    # written right after it ("L-alanyl-L-valyl-..."); a
                    # word-leading "trans" / "(+-)" describes the word's root.
                    target = head
                    if not leading or label.upper() in _FISCHER:
                        owner = owners.get(next((t.index for t in tokens[idx + 1:]
                                                 if owners.get(t.index) is not None), -1))
                        if owner is not None and owner.kind == "part":
                            target = by_key.get(owner.span, head)
                    parent = self.part_node.get(target.key, (None, []))[0] if target else None
                    self.add("stereo", label, span, parent=parent, lights=[],
                             line=describe_stereo(label, within))
            if bridge is not None:
                # "4,5alpha-epoxy": the marks written right before a bridge name the
                # positions it bridges.
                lit = {a for n in self.nodes[first_new:] for a in n["lights"]}
                if lit:
                    bridge["lights"] = sorted(lit)

    def token_locant(self, loc: str, span: Span, head: Optional[_WrittenPart],
                     nxt: Optional[_WrittenPart] = None, bridge: Optional[dict] = None) -> None:
        if nxt is not None and nxt.kind == "substituent" and nxt.key in self.part_node:
            copies = [c for c in nxt.copies if c.locant == loc]
            if copies:
                self.add("locant", loc, span, parent=self.part_node[nxt.key][0],
                         lights=[a for c in copies for a in c.atoms],
                         line=describe_locant("substituent", loc))
                return
        suffix = self.suffix_node.get(head.key) if head else None
        # A split-out number goes to the suffix only when it is one of the suffix's own
        # locants ("3,17beta-diol"); "4" of "4,5alpha-epoxy...-6-one" is the bridge's.
        if suffix is not None and bridge is not None and loc not in set(suffix[2].values()):
            atoms = self.part_node[head.key][1]
            self.add("locant", loc, span, parent=bridge["id"], lights=self.with_locant(atoms, loc),
                     line=describe_locant("position", loc))
            return
        if suffix is not None:
            node, atoms, locants = suffix
            parent_atoms = [a for a in self.part_node[head.key][1] if a not in atoms]
            lights = [a for a in atoms if locants.get(a) == loc] + self.with_locant(parent_atoms, loc)
            self.add("locant", loc, span, parent=node, lights=lights, line=describe_locant("suffix", loc))
            return
        node, atoms = self.part_node.get(head.key, (None, [])) if head else (None, [])
        self.add("locant", loc, span, parent=node, lights=self.with_locant(atoms, loc),
                 line=describe_locant("position", loc))


def _bridge_prefixes_to_the_root(trace: Trace, owners: dict) -> None:
    """A ring-bridge prefix OPSIN used up ("4,5-epoxy" in "4,5-epoxy-17-methyl|
    morphinane") modifies the parent ring system it is written before. The
    written-neighbour rule hands it to the next KEPT token, which is the
    substituent in between ("methyl"). Move it, and the locants written right
    before it, to the next root part."""
    roots = {p.span for p in trace.parts if p.kind == "root" and p.span is not None}
    for tok in trace.tokens:
        if tok.kind != "fusedRingBridge" or tok.owner is not None or owners.get(tok.index) is None:
            continue
        current = owners[tok.index]
        target = next((owners[t.index] for t in trace.tokens[tok.index + 1:]
                       if owners.get(t.index) is not None and owners[t.index].kind == "part"
                       and owners[t.index].span in roots), None)
        if target is None or target == current:
            continue
        owners[tok.index] = target
        j = tok.index - 1
        while j >= 0 and trace.tokens[j].kind in LOCANT_KINDS | {"hyphen"}:
            if owners.get(trace.tokens[j].index) == current:
                owners[trace.tokens[j].index] = target
            j -= 1


def build_nodes(trace: Trace) -> list[dict]:
    trace = adopt_orphan_tokens(trace)
    parts = _written_parts(trace)
    b = _Builder(trace, parts)
    by_key = b.by_key
    owners = assign_owners(trace.tokens)
    _bridge_prefixes_to_the_root(trace, owners)
    loose: list[tuple[WrittenToken, Optional[Span]]] = []
    for tok in trace.tokens:
        if tok.index not in owners or tok.kind == STEREO_KIND:
            continue                                   # glue; stereo is handled by b.stereo
        owner = owners[tok.index]
        if owner is not None and owner.kind == "part" and owner.span in by_key:
            by_key[owner.span].tokens.append(tok)
        else:
            loose.append((tok, owner.span if owner is not None and owner.kind == "bracket" else None))
    for w in parts:
        w.tokens.sort(key=lambda t: t.span[0])
    for w in sorted(parts, key=lambda w: (w.tokens[0].span[0] if w.tokens else 10**9)):
        if w.key is None or not w.tokens:
            b.unplaced_part(w)
        elif w.kind == "substituent":
            b.substituent(w)
        elif w.kind == FUNCTIONAL_KIND:
            b.functional(w)
        else:
            b.root(w)
    for tok, bracket in loose:
        if bracket is not None:
            b.bracket_token(tok, bracket)
        else:
            b.orphan(tok)
    b.stereo(owners)
    return b.nodes
