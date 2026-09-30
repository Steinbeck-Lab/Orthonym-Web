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

What a node lights is never a guess:

* a position locant lights the copy OPSIN put at that locant. When no copy
  sits there, the locant is read by structure, never by "any atom in the word
  that carries the number": on a multiplicative bridge ("4,4'-methylene|bis(...)",
  a substituent bonded to two copies of the root) it names the atoms of the
  multiplied root that the bridge is bonded to; otherwise it is the
  substituent's own attachment atom ("2-pyridyl"), its own ring heteroatom
  ("1,3-benzodioxol"), the atom of the parent the whole substituent chain is
  bonded to ("2-acetyloxy|benzoic acid"), or else an atom of its own part;
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

from .glossary import GENERIC_TOKEN_LINE, describe_locant, describe_part, describe_token
from .label_rules import (
    CONTEXTUAL, GLUE, LOCANT_KINDS, covered_positions, indicated_h_items,
    label_span, locant_items, resolve_roles, root_spans, stereo_items,
)
from .opsin_trace import STEREO_KIND, Span, Trace, TracePart, WrittenToken
from .root_split import split_root
from .token_owner import Owner, adopt_orphan_tokens, assign_owners, innermost_bracket, written_brackets

PART_NODE_KINDS = frozenset({"substituent", "parent", "suffix"})
_NODE_KIND = {
    "locant": "locant", "colonOrSemiColonDelimitedLocant": "locant", "spiroLocant": "locant",
    "multiplier": "multiplier", "ringAssemblyMultiplier": "multiplier",
    "hydro": "hydro", "indicatedHydrogen": "indicated_h", STEREO_KIND: "stereo",
}
_LINE_KINDS = frozenset({"multiplier", "ringAssemblyMultiplier", "hydro", "fusion", "vonBaeyer", "spiro"})
# "2S", "4aR", "9Z", relative "1S*", steroid "3beta" -> (locant, descriptor).
_STEREO_MARK = re.compile(r"^(\d+[a-z]?'*)([RSrs]\*?|[EZ]|alpha|beta)$")
# A descriptor with no locant ("(S)-oxolan-3-yl", "(E)-...").
_BARE_DESCRIPTOR = re.compile(r"^([RSrs]\*?|[EZ])$")
_ADDED_H = re.compile(r"^(\d+[a-z]?'*)H$")
_BARE_LOCANT = re.compile(r"^\d+[a-z]?'*$")
# Fischer D/L always prefix the part written right after them ("L-alanyl").
_FISCHER = frozenset({"D", "L", "DL"})


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


def _stereo_atoms(smiles: str) -> tuple[set, set]:
    """(stereocentres, atoms on a stereo double bond) of the traced molecule."""
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return set(), set()
    centres = {i for i, _ in Chem.FindMolChiralCenters(
        mol, includeUnassigned=True, useLegacyImplementation=False)}
    bonds = set()
    for bond in mol.GetBonds():
        if bond.GetStereo() != Chem.BondStereo.STEREONONE:
            bonds.update((bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()))
    return centres, bonds


def _attachment_written_inside(trace: Trace, key: Optional[Span]) -> bool:
    """True when a substituent writes its own attachment point after its group
    ("pentan-3-yl", "pyridin-2-yl": the -3- / -2-), so a number in front can
    only be another's. Decided by WRITTEN ORDER: a locant token between the
    part's group token and its last own token. OPSIN leaves the attachment
    locant of a ring "-yl" unowned, so the owner cannot be asked."""
    mine = [t for t in trace.tokens if t.owner == key]
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
        mine = [t for t in trace.tokens if t.owner == key]
        if not mine:
            break
        end = max(end, max(t.span[1] for t in mine))
        nxt = next((t for t in trace.tokens[max(t.index for t in mine) + 1:] if t.kind != "hyphen"), None)
        key = nxt.owner if nxt is not None and nxt.kind == "group" and nxt.owner in subs else None
    return end


def _chain_is_bracketed(trace: Trace, key: Optional[Span]) -> bool:
    """True when the part's leading locant and the whole run of substituents
    it starts ("(2-pyridylmethyl)", "(2-acetyloxyethyl)") sit inside one
    bracket pair. An unbracketed chain ("2-pyridyloxybenzoic acid") puts its
    leading locant on the parent (IUPAC P-16.5.1)."""
    mine = [t for t in trace.tokens if t.owner == key]
    core = next((t for t in mine if t.kind == "group"), None)
    if core is None:
        return False
    # The locant run written directly in front of the group ("2-" in "2-pyridyl"):
    # its tokens belong to no part (owner None), so walk back from the group.
    lead, j = None, core.index - 1
    while j >= 0 and trace.tokens[j].kind in LOCANT_KINDS | {"hyphen"}:
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


def _joined_to_next_substituent(trace: Trace, key: Optional[Span]) -> bool:
    """True when a substituent is followed directly (hyphens skipped) by
    another substituent's group token it is joined to ("acetyl|oxy",
    "pyridyl|methyl")."""
    mine = [t for t in trace.tokens if t.owner == key]
    if key is None or not mine:
        return False
    nxt = next((t for t in trace.tokens[max(t.index for t in mine) + 1:] if t.kind != "hyphen"), None)
    return (nxt is not None and nxt.kind == "group" and nxt.owner not in (None, key)
            and any(p.span == nxt.owner and p.kind == "substituent" for p in trace.parts))


class _Builder:
    def __init__(self, trace: Trace, parts: list[_WrittenPart]):
        self.t = trace
        self.parts = parts
        self.nodes: list[dict] = []
        self.covered = covered_positions(trace.tokens)
        self.by_index = {a.index: a for a in trace.atoms}
        self.part_node: dict[Span, tuple[str, list[int]]] = {}   # key -> (node id, atoms)
        self.suffix_node: dict[Span, tuple[str, list[int], dict]] = {}  # root key -> (id, atoms, locants)
        self.centres, self.double = _stereo_atoms(trace.smiles)
        self.mol = Chem.MolFromSmiles(trace.smiles)
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

    def spiro_lookup(self, tokens, i: int, atoms, loc: str) -> str:
        """The locant as OPSIN numbers it. In spiro[A-x,y'-B] every locant
        written after the spiro locants belongs to a later component, and
        OPSIN primes those atoms ("6-oxa" in the second component is 6'): the
        bare number would light the first component's atom."""
        if not any(t.kind == "polyCyclicSpiro" for t in tokens) or loc.endswith("'"):
            return loc
        primes = sum(1 for t in tokens[:i] if t.kind == "spiroLocant")
        if tokens[i].kind == "spiroLocant" or not primes:
            return loc
        primed = loc + "'" * primes
        return primed if self.with_locant(atoms, primed) else loc

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
                 line=describe_part(kind, w.kind, None, len(set(owns)), copies=len(w.copies)))

    def substituent(self, w: _WrittenPart) -> None:
        roles = resolve_roles(w.tokens, "substituent", len(w.copies))
        span = label_span(self.t.text, w.tokens, roles, self.covered, w.key)
        label = self.text(span)
        owns = self.atoms_of(w)
        node = self.add("substituent", label, span, owns=owns, lights=owns, copies=len(w.copies),
                        line=describe_part("substituent", label, None, len(set(owns)), copies=len(w.copies)))
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
            split = split_root(self.t, c.atoms)
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
                          line=describe_part("parent", label, None, len(set(parent_atoms)), copies=len(w.copies)))
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
                              line=describe_part("suffix", s_label, None, len(set(suffix_atoms))))
            self.suffix_node[w.key] = (suffix, suffix_atoms, suffix_locants)
            tail = [(t, r) for t, r in zip(w.tokens, roles) if t.index in run]
            self.children(suffix, w, [t for t, _ in tail], [r for _, r in tail], parent_atoms, lights,
                          mode="suffix", suffix_atoms=suffix_atoms, suffix_locants=suffix_locants)

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
                for loc, sub in items:
                    added = _ADDED_H.match(loc)
                    if added:
                        # "2(1H)": hydrogen added at position 1 of the parent.
                        at = self.spiro_lookup(tokens, i, atoms, added.group(1))
                        hit = self.with_locant(atoms, at)
                        element = self.by_index[hit[0]].element if len(hit) == 1 else None
                        self.add("indicated_h", loc, sub, parent=owner, lights=hit,
                                 line=describe_locant("modifier", at, element))
                        continue
                    lights, line = self.locant(self.spiro_lookup(tokens, i, atoms, loc), i < first_core,
                                               target, mode, atoms, w.copies,
                                               used_copies, suffix_atoms, suffix_locants or {},
                                               written[loc], w, [x for x, _ in items])
                    counted.update(lights)
                    self.add("locant", loc, sub, parent=owner, lights=lights, line=line)
            elif tok.kind == "indicatedHydrogen":
                for loc, sub in indicated_h_items(self.t.text, tok.span):
                    loc = self.spiro_lookup(tokens, i, atoms, loc)
                    hit = self.with_locant(atoms, loc)
                    element = self.by_index[hit[0]].element if len(hit) == 1 else None
                    self.add("indicated_h", self.text(sub), sub, parent=owner, lights=hit,
                             line=describe_locant("modifier", loc, element))
            elif tok.kind in _LINE_KINDS:
                span = self.trim(tok.span)
                self.add(_NODE_KIND.get(tok.kind, "token"), self.text(span), span, parent=owner,
                         lights=counted or token_lights, line=describe_token(tok.kind, self.text(span)))
            elif roles[i] == "prefix":
                span = self.trim(tok.span)
                line = describe_token(tok.kind, self.text(span)) or GENERIC_TOKEN_LINE.format(text=self.text(span))
                self.add(_NODE_KIND.get(tok.kind, "token"), self.text(span), span, parent=owner,
                         lights=token_lights, line=line)
            elif roles[i] == "core":
                counted = set()

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
        return len([r for r in self.mol.GetRingInfo().AtomRings() if set(r) <= set(own)]) == 1

    def linker_atom(self, atom: int) -> bool:
        part = self.part_of.get(atom)
        return (part is not None and part.kind == "substituent"
                and any(re.match(r"^[A-Z][a-z]?'*$", loc) for loc in self.by_index[atom].locants))

    def in_ring(self, atom: int) -> bool:
        return (self.mol is not None and atom < self.mol.GetNumAtoms()
                and self.mol.GetAtomWithIdx(atom).IsInRing())

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
        inside = _attachment_written_inside(self.t, w.key)
        if _joined_to_next_substituent(self.t, w.key) and not _chain_is_bracketed(self.t, w.key):
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
            if _joined_to_next_substituent(self.t, w.key):
                # (a bracketed chain only: an unbracketed one returned above)
                attach = [a for a in attach if self.in_ring(a) and not self.implicit_attachment(own, a, loc)]
            if attach:
                return attach
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
        by_key = {p.key: p for p in self.parts if p.key is not None}
        seen, atoms, part = {w.key}, set(self.atoms_of(w)), w
        while True:
            edge = self.edge(atoms)
            # A linker carbon (methyl, methoxy's CH2) carries its number beside
            # an element symbol ("1/C"): that is not a position the chain hangs on.
            hit = [a for a in self.carrying(edge, loc) if not self.linker_atom(a)]
            if hit:
                return hit
            last = max(t.index for t in part.tokens) if part.tokens else -1
            nxt = next((t for t in self.t.tokens[last + 1:] if t.kind != "hyphen"), None)
            part = by_key.get(nxt.owner) if nxt is not None and nxt.kind == "group" else None
            if part is None or part.kind != "substituent" or part.key in seen:
                return []
            seen.add(part.key)
            atoms |= set(self.atoms_of(part))

    def locant(self, loc, leading, target, mode, atoms, copies, used, suffix_atoms, suffix_locants,
               written, w, token_locs):
        if target is not None and target.kind == "hydro":
            hit = self.with_locant(atoms, loc)
            element = self.by_index[hit[0]].element if len(hit) == 1 else None
            return hit, describe_locant("modifier", loc, element)
        if (mode == "substituent" and self.carbohydrate_atoms is not None
                and loc.lower() in ("alpha", "beta")):
            return (self.anomeric_carbon(self.carbohydrate_atoms, attached=True),
                    describe_locant("position", loc, anomer=True))
        if mode == "substituent" and leading:
            at_loc = [c for c in copies if c.locant == loc]
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
            return self.anomeric_carbon(self.carbohydrate_atoms), describe_locant("position", loc, anomer=True)
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
            for loc, sub in locant_items(self.t.text, tok.span):
                lights = atoms
                if bridge:
                    lights = self.carrying(roots, loc) or atoms
                self.add("locant", loc, sub, lights=lights, line=describe_locant("substituent", loc))
            return
        span = self.trim(tok.span)
        label = self.text(span)
        line = describe_token(tok.kind, label) or GENERIC_TOKEN_LINE.format(text=label)
        self.add(_NODE_KIND.get(tok.kind, "token"), label, span, lights=atoms, line=line)

    def orphan(self, tok: WrittenToken) -> None:
        span = self.trim(tok.span)
        label = self.text(span)
        self.add(_NODE_KIND.get(tok.kind, "token"), label, span,
                 line=describe_token(tok.kind, label) or GENERIC_TOKEN_LINE.format(text=label))

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
        by_key = {w.key: w for w in self.parts if w.key is not None}
        for idx, tok in enumerate(tokens):
            if tok.kind != STEREO_KIND:
                continue
            scope = innermost_bracket(brackets, tok.span[0])
            if scope is not None:
                scope_parts = [w for w in self.parts if w.tokens and
                               scope[0] < w.tokens[0].span[0] < scope[1]]
                direct = [t for t in tokens if t.owner is not None and
                          innermost_bracket(brackets, t.span[0]) == scope]
                head = by_key.get(direct[-1].owner) if direct else None
            else:
                word = self.word(tok.span[0])
                scope_parts = [w for w in self.parts if w.tokens and self.word(w.tokens[0].span[0]) == word]
                roots = [w for w in scope_parts if w.kind == "root"]
                head = roots[0] if roots else (scope_parts[-1] if scope_parts else None)
            leading = not any(p.kind not in GLUE and p.kind != STEREO_KIND
                              and self.word(p.span[0]) == self.word(tok.span[0]) for p in tokens[:idx])
            for label, span in stereo_items(self.t.text, tok.span):
                m = _STEREO_MARK.match(label)
                if m:
                    key, atom = self.stereo_atom(m.group(1), m.group(2).rstrip("*"), scope_parts, head)
                    owner_key = key if key is not None else (head.key if head else None)
                    parent = self.part_node.get(owner_key, (None, []))[0]
                    self.add("stereo", label, span, parent=parent,
                             lights=[atom] if atom is not None else [],
                             line=describe_token(STEREO_KIND, label))
                elif _BARE_DESCRIPTOR.match(label) and head is not None:
                    # No locant: light the stereocentre (or stereo double
                    # bond) of the scope's main part only if it has exactly one.
                    pool = self.double if label in ("E", "Z") else self.centres
                    hits = sorted(a for a in self.atoms_of(head) if a in pool)
                    single = hits[:1] if (len(hits) == 1 or (label in ("E", "Z") and len(hits) == 2)) else []
                    self.add("stereo", label, span, parent=self.part_node.get(head.key, (None, []))[0],
                             lights=single, line=describe_token(STEREO_KIND, label))
                elif _BARE_LOCANT.match(label):
                    # A locant listed with a mark: "3,17beta-diol" (it is the
                    # suffix's own locant) or "11beta,17,21-trihydroxy" (it is
                    # the substituent's). What the list precedes decides.
                    after = next((t for t in tokens[idx + 1:] if owners.get(t.index) is not None), None)
                    nxt = None
                    if after is not None and owners[after.index].kind == "part":
                        nxt = by_key.get(owners[after.index].span)
                    self.token_locant(label, span, head, nxt)
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
                             line=describe_token(STEREO_KIND, label))

    def token_locant(self, loc: str, span: Span, head: Optional[_WrittenPart],
                     nxt: Optional[_WrittenPart] = None) -> None:
        if nxt is not None and nxt.kind == "substituent" and nxt.key in self.part_node:
            copies = [c for c in nxt.copies if c.locant == loc]
            if copies:
                self.add("locant", loc, span, parent=self.part_node[nxt.key][0],
                         lights=[a for c in copies for a in c.atoms],
                         line=describe_locant("substituent", loc))
                return
        suffix = self.suffix_node.get(head.key) if head else None
        if suffix is not None:
            node, atoms, locants = suffix
            parent_atoms = [a for a in self.part_node[head.key][1] if a not in atoms]
            lights = [a for a in atoms if locants.get(a) == loc] + self.with_locant(parent_atoms, loc)
            self.add("locant", loc, span, parent=node, lights=lights, line=describe_locant("suffix", loc))
            return
        node, atoms = self.part_node.get(head.key, (None, [])) if head else (None, [])
        self.add("locant", loc, span, parent=node, lights=self.with_locant(atoms, loc),
                 line=describe_locant("position", loc))


def build_nodes(trace: Trace) -> list[dict]:
    trace = adopt_orphan_tokens(trace)
    parts = _written_parts(trace)
    b = _Builder(trace, parts)
    by_key = {w.key: w for w in parts if w.key is not None}
    owners = assign_owners(trace.tokens)
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
        else:
            b.root(w)
    for tok, bracket in loose:
        if bracket is not None:
            b.bracket_token(tok, bracket)
        else:
            b.orphan(tok)
    b.stereo(owners)
    return b.nodes


def _chain_prefixes(trace: Trace, key: Optional[Span]) -> list[set[int]]:
    """Atom sets of the growing run of substituents written one after another
    from the part `key` ("acetyl", "acetyl+oxy", "acetyl+oxy+ethyl")."""
    by_key = {p.span: p for p in trace.parts if p.span is not None and p.kind == "substituent"}
    out, atoms, seen = [], set(), set()
    while key is not None and key in by_key and key not in seen:
        seen.add(key)
        atoms = atoms | {a for p in trace.parts if p.span == key for a in p.atoms}
        out.append(set(atoms))
        mine = [t for t in trace.tokens if t.owner == key]
        nxt = next((t for t in trace.tokens[max(t.index for t in mine) + 1:] if t.kind != "hyphen"), None) \
            if mine else None
        key = nxt.owner if nxt is not None and nxt.kind == "group" else None
    return out


def _written_list(text: str, nodes: list[dict], node: dict) -> list[str]:
    """The labels of the locant nodes written in one comma list with `node`."""
    same = sorted((x for x in nodes if x["kind"] == "locant" and x["parent"] == node["parent"] and x["span"]),
                  key=lambda x: x["span"][0])
    run: list[dict] = []
    for x in same:
        if run and text[run[-1]["span"][1]:x["span"][0]] not in (",", ", "):
            if node in run:
                break
            run = []
        run.append(x)
    return [x["label"] for x in run] if node in run else [node["label"]]


def _holds_anomeric_bonds(mol, atom: int, pool: set[int]) -> bool:
    """A ring carbon of a sugar with a ring oxygen AND an exocyclic bond to an
    oxygen of the sugar or to whatever the sugar is attached to (outside
    `pool`): the only atom an anomer mark may light. Read off the molecule,
    not from the builder."""
    a = mol.GetAtomWithIdx(atom)
    if a.GetSymbol() != "C" or not a.IsInRing():
        return False
    ring_o = exo = False
    for n in a.GetNeighbors():
        in_ring = mol.GetBondBetweenAtoms(atom, n.GetIdx()).IsInRing()
        if in_ring and n.GetSymbol() == "O" and n.GetIdx() in pool:
            ring_o = True
        elif not in_ring and (n.GetIdx() not in pool or n.GetSymbol() == "O"):
            exo = True
    return ring_o and exo


def foreign_lights(trace: Trace, nodes: list[dict]) -> list[tuple[str, list[int]]]:
    """The lit-atom gate: (label, atoms) for every locant node that lights an
    atom it has no claim on. Derived from the trace and the node list alone
    (not from the builder), so the builder cannot grade itself.

    A locant that is a child of a part may light: atoms of that part's own
    written root/substituent (every copy); a copy OPSIN placed at that locant;
    or an atom carrying the locant that the part's whole substituent chain is
    bonded to (the parent position it hangs on, or a multiplied root's
    bridged position). A bracket's own locant (no parent) may light parts
    written inside it, or atoms carrying the locant."""
    trace = adopt_orphan_tokens(trace)
    mol = Chem.MolFromSmiles(trace.smiles)
    by_atom = {a.index: a for a in trace.atoms}
    part_of = {a: p for p in trace.parts for a in p.atoms}
    by_id = {n["id"]: n for n in nodes}
    owners = assign_owners(trace.tokens)
    owner_node = {a: n for n in nodes if n["kind"] in PART_NODE_KINDS for a in n["owns"]}

    def nbrs(a):
        return [x.GetIdx() for x in mol.GetAtomWithIdx(a).GetNeighbors()] if mol is not None else []

    bad = []
    for n in nodes:
        if n["kind"] != "locant" or not n["lights"]:
            continue
        label, lit = n["label"], set(n["lights"])
        if n["parent"] is None:
            after = n["span"][0] if n["span"] else 0
            ok = all(label in by_atom[a].locants or (
                a in owner_node and owner_node[a]["span"] and owner_node[a]["span"][0] > after) for a in lit)
        else:
            parent = by_id[n["parent"]]
            seed = set(parent["owns"]) or set(parent["lights"])
            family = {a for p in trace.parts if seed & set(p.atoms) for a in p.atoms}
            comp, stack = set(family), list(family)
            while stack:
                for x in nbrs(stack.pop()):
                    if x not in comp and part_of.get(x) is not None and part_of[x].kind == "substituent":
                        comp.add(x)
                        stack.append(x)
            edge = {x for a in comp for x in nbrs(a) if x not in comp and label in by_atom[x].locants}
            own_key = next((p.span for p in trace.parts if p.kind == "substituent"
                            and p.atoms and set(p.atoms) <= set(parent["owns"])), None)
            for prefix in _chain_prefixes(trace, own_key):
                edge |= {x for a in prefix for x in nbrs(a) if x not in prefix and label in by_atom[x].locants}
            placed = {a for p in trace.parts if p.locant == label for a in p.atoms}
            ok = lit <= family | placed | edge
            key = next((p.span for p in trace.parts if p.kind == "substituent"
                        and p.atoms and set(p.atoms) <= set(parent["owns"])), None)
            if (mol is not None and key is not None and label.lower() in ("alpha", "beta")
                    and any(t.kind == "carbohydrateRingSize" and owners.get(t.index) == Owner("part", key)
                            for t in trace.tokens)):
                # A glycosyl substituent's anomer mark may light exactly one
                # atom: the ring carbon holding the ring O and the glycosidic bond.
                if not (len(lit) == 1 and _holds_anomeric_bonds(mol, next(iter(lit)), set(parent["owns"]))):
                    bad.append((label, sorted(lit)))
                continue
            chained = parent["kind"] == "substituent" and _joined_to_next_substituent(trace, key)
            # A ring substituent joined to a linker ("2-pyridyl|methyl"): the
            # number is the ring's own attachment atom, so the atom it bonds
            # out of -- a ring atom carrying the number -- is the only claim;
            # lighting the parent's atom of the same number is foreign.
            ring_attach = set()
            core_tok = next((t for t in trace.tokens if t.owner == key and t.kind == "group"), None)
            at_front = bool(core_tok is not None and n["span"] and n["span"][1] <= core_tok.span[0]
                            and "hydrogen" not in n["line"])
            # An UNBRACKETED chain ("2-pyridyloxybenzoic acid", "1-phenylmethoxynaphthalene"):
            # the number in front is the parent's position, whatever the ring
            # or a linker carries -- no atom of the chain may be lit for it.
            unbracketed = (parent["kind"] == "substituent" and _joined_to_next_substituent(trace, key)
                           and not _chain_is_bracketed(trace, key))
            if unbracketed and at_front:
                ok = ok and not ((lit - placed) & comp)
            elif chained and not _attachment_written_inside(trace, key) and mol is not None:
                ring_attach = {a for a in seed if label in by_atom[a].locants
                               and mol.GetAtomWithIdx(a).IsInRing() and any(x not in seed for x in nbrs(a))
                               and not (label == "1" and all(by_atom[x].element == "C" for x in seed)
                                        and len([r for r in mol.GetRingInfo().AtomRings() if set(r) <= seed]) == 1)}
            leading = bool(ring_attach and at_front)
            if leading:
                ok = ok and lit - placed <= ring_attach
                chained = False
            if ok and chained:
                core = next((t for t in trace.tokens if t.owner == key and t.kind == "group"), None)
                if (core is not None and n["span"] and n["span"][1] <= core.span[0]
                        and "hydrogen" not in n["line"]
                        and any(a in seed and (by_atom[a].element == "C" or any(x not in seed for x in nbrs(a)))
                                for a in lit - placed)):
                    ok = False
            # "1,4-phenylene": when the part itself carries EVERY locant of
            # the list and this locant's own atom is where it is bonded out,
            # the list is its own numbering, never a bridge's.
            if ok and not chained and not lit <= family | placed:
                own_attach = [a for a in family if label in by_atom[a].locants
                              and any(x not in family for x in nbrs(a))]
                siblings = _written_list(trace.text, nodes, n)
                if own_attach and all(any(x in by_atom[a].locants for a in family) for x in siblings):
                    ok = False
        if not ok:
            bad.append((label, sorted(lit)))
    return bad
