"""The lit-atom gate: an independent check of what build_nodes lights.

Test- and census-only (the response path never imports it). It exists so the
builder cannot grade itself: ``foreign_lights`` and ``oxy_pair_allowed`` re-derive
what a locant node may light from the trace (OPSIN's parts, the written tokens) and
the bonds of the traced molecule alone, by their own route and not through
``app.explain_tree._Builder``. A defect in the builder's rule therefore does not
hide itself here. Keep it that way: do not route this module through the builder's
lighting rules (it shares only the predicates that read the written name:
``attachment_written_inside``, ``chain_is_bracketed``, ``joined_to_next_substituent``).
"""

from __future__ import annotations

import re
from typing import Optional, Sequence

from rdkit import Chem

from .explain_tree import PART_NODE_KINDS, attachment_written_inside, chain_is_bracketed, joined_to_next_substituent
from .label_rules import ELEMENT_LOCANT, LOCANT_KINDS, NUMBER_LOCANT, locant_items
from .opsin_trace import Span, Trace
from .token_owner import Owner, adopt_orphan_tokens, assign_owners, bracket_end, next_nonhyphen, tokens_of


def _chain_prefixes(trace: Trace, key: Optional[Span]) -> list[set[int]]:
    """Atom sets of the growing run of substituents written one after another
    from the part `key` ("acetyl", "acetyl+oxy", "acetyl+oxy+ethyl")."""
    by_key = {p.span: p for p in trace.parts if p.span is not None and p.kind == "substituent"}
    out, atoms, seen = [], set(), set()
    while key is not None and key in by_key and key not in seen:
        seen.add(key)
        atoms = atoms | {a for p in trace.parts if p.span == key for a in p.atoms}
        out.append(set(atoms))
        mine = tokens_of(trace, key)
        nxt = next_nonhyphen(trace.tokens, max(t.index for t in mine)) if mine else None
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


_PAIR_IN_ONE_TOKEN = re.compile(r"(\d+[a-z]?'*)-([A-Z][a-z]?'*)(?=-|$)")


def oxy_pair_allowed(trace: Trace, node: dict, parent: Optional[dict],
                     nodes: Sequence[dict] = (), mol: Optional[Chem.Mol] = None) -> Optional[set[int]]:
    """For a locant node that is half of an "n-O-" pair ("4-O-beta-D-galactopyranosyl",
    "6-O-acetyl", "2,3,4-tri-O-acetyl", "6-O-(alpha-L-rhamnopyranosyl)") in front of the
    substituent `parent` -- or, for a bracket's own locant (`parent` None), in front of
    the bracket, whose parts are read from `nodes` -- the atoms it may light, else None
    (not such a node). A pair names the PARENT's atom of that element, bonded to the
    substituent chain, and the parent carbon carrying the number that atom is bonded
    to; neither may be an atom of the substituent itself. Read from the written tokens
    and the bonds, not from the builder. `mol` is the parsed traced SMILES when the
    caller already holds it."""
    if not node["span"]:
        return None
    text, tokens = trace.text, trace.tokens
    if parent is not None:
        if parent["kind"] != "substituent" or not parent["span"] or node["span"][1] > parent["span"][0]:
            return None
        inside = set(parent["owns"])
    else:
        # a bracket's own locant: the bracket opens right after the written token
        at = next((t.span[1] for t in tokens if t.kind in LOCANT_KINDS and t.span[0] <= node["span"][0] < t.span[1]), None)
        while at is not None and at < len(text) and text[at] in "-":
            at += 1
        end = bracket_end(text, at) if at is not None else None
        if end is None:
            return None
        inside = {a for m in nodes if m["kind"] in PART_NODE_KINDS and m["span"]
                  and at < m["span"][0] and m["span"][1] <= end for a in m["owns"]}
    tok = next((t for t in tokens if t.kind in LOCANT_KINDS and t.span[0] <= node["span"][0] < t.span[1]), None)
    if tok is None:
        return None
    label = node["label"]
    raw = text[tok.span[0]:tok.span[1]]

    def around(index: int, step: int):
        j = index + step
        while 0 <= j < len(tokens) and tokens[j].kind in ("hyphen", "multiplier"):
            j += step
        return tokens[j] if 0 <= j < len(tokens) else None

    role, symbol, numbers = None, None, []
    m = next((m for m in _PAIR_IN_ONE_TOKEN.finditer(raw)
              if tok.span[0] + m.start(1) == node["span"][0] or tok.span[0] + m.start(2) == node["span"][0]), None)
    if m is not None:
        symbol, numbers = m.group(2), [m.group(1)]
        role = "number" if tok.span[0] + m.start(1) == node["span"][0] else "element"
    elif ELEMENT_LOCANT.match(label) and re.fullmatch(r"[A-Z][a-z]?'*-?", raw):
        before = around(tok.index, -1)
        if before is not None and before.kind in LOCANT_KINDS:
            listed = [x for x, _ in locant_items(text, before.span)]
            if listed and all(NUMBER_LOCANT.match(x) for x in listed):
                role, symbol, numbers = "element", label, listed
    elif NUMBER_LOCANT.match(label):
        after = around(tok.index, 1)
        if after is not None and after.kind in LOCANT_KINDS:
            listed = [x for x, _ in locant_items(text, after.span)]
            if len(listed) == 1 and ELEMENT_LOCANT.match(listed[0]):
                role, symbol, numbers = "number", listed[0], [label]
    if role is None:
        return None
    if mol is None:
        mol = Chem.MolFromSmiles(trace.smiles)
    if mol is None:
        return set()
    part_of = {a: p for p in trace.parts for a in p.atoms}
    chain = set(inside)
    stack = list(chain)
    while stack:
        for x in mol.GetAtomWithIdx(stack.pop()).GetNeighbors():
            q = part_of.get(x.GetIdx())
            if x.GetIdx() not in chain and q is not None and q.kind == "substituent":
                chain.add(x.GetIdx())
                stack.append(x.GetIdx())
    joined = {y.GetIdx() for a in chain for y in mol.GetAtomWithIdx(a).GetNeighbors()
              if y.GetIdx() not in chain and y.GetSymbol() == symbol.rstrip("'")}
    allowed: set[int] = set()
    for y in joined:
        for x in mol.GetAtomWithIdx(y).GetNeighbors():
            if x.GetIdx() in chain:
                continue
            wanted = numbers if role == "element" else [label]
            if any(n in trace.atoms[x.GetIdx()].locants for n in wanted):
                allowed.add(x.GetIdx() if role == "number" else y)
    return allowed


def foreign_lights(trace: Trace, nodes: list[dict],
                   mol: Optional[Chem.Mol] = None) -> list[tuple[str, list[int]]]:
    """The lit-atom gate: (label, atoms) for every locant node that lights an
    atom it has no claim on. Derived from the trace and the node list alone
    (not from the builder), so the builder cannot grade itself.

    A locant that is a child of a part may light: atoms of that part's own
    written root/substituent (every copy); a copy OPSIN placed at that locant;
    or an atom carrying the locant that the part's whole substituent chain is
    bonded to (the parent position it hangs on, or a multiplied root's
    bridged position). A bracket's own locant (no parent) may light parts
    written inside it, or atoms carrying the locant. `mol` is the parsed traced SMILES
    when the caller already holds it."""
    trace = adopt_orphan_tokens(trace)
    if mol is None:
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
        pair = oxy_pair_allowed(trace, n, by_id[n["parent"]] if n["parent"] is not None else None, nodes, mol)
        if pair is not None:
            if not lit <= pair:
                bad.append((label, sorted(lit)))
            continue
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
            key = next((p.span for p in trace.parts if p.kind == "substituent"
                        and p.atoms and set(p.atoms) <= set(parent["owns"])), None)
            for prefix in _chain_prefixes(trace, key):
                edge |= {x for a in prefix for x in nbrs(a) if x not in prefix and label in by_atom[x].locants}
            placed = {a for p in trace.parts if p.locant == label for a in p.atoms}
            ok = lit <= family | placed | edge
            if (mol is not None and key is not None and label.lower() in ("alpha", "beta")
                    and any(t.kind == "carbohydrateRingSize" and owners.get(t.index) == Owner("part", key)
                            for t in trace.tokens)):
                # A glycosyl substituent's anomer mark may light exactly one
                # atom: the ring carbon holding the ring O and the glycosidic bond.
                if not (len(lit) == 1 and _holds_anomeric_bonds(mol, next(iter(lit)), set(parent["owns"]))):
                    bad.append((label, sorted(lit)))
                continue
            chained = parent["kind"] == "substituent" and joined_to_next_substituent(trace, key)
            # A ring substituent joined to a linker ("2-pyridyl|methyl"): the
            # number is the ring's own attachment atom, so the atom it bonds
            # out of -- a ring atom carrying the number -- is the only claim;
            # lighting the parent's atom of the same number is foreign.
            ring_attach = set()
            core = next((t for t in tokens_of(trace, key) if t.kind == "group"), None)
            at_front = bool(core is not None and n["span"] and n["span"][1] <= core.span[0]
                            and "hydrogen" not in n["line"])
            # An UNBRACKETED chain ("2-pyridyloxybenzoic acid", "1-phenylmethoxynaphthalene"):
            # the number in front is the parent's position, whatever the ring
            # or a linker carries -- no atom of the chain may be lit for it.
            unbracketed = (parent["kind"] == "substituent" and joined_to_next_substituent(trace, key)
                           and not chain_is_bracketed(trace, key))
            if unbracketed and at_front:
                # ...so the only atoms it may light are ones a prefix of the
                # written chain is bonded to: the parent position, or the atom
                # of a later chain member that carries the number ("2-acetyloxy|ethyl
                # acetate": ethyl C2). Never the chain's own atoms or a linker.
                reach = set()
                for prefix in _chain_prefixes(trace, key):
                    reach |= {x for a in prefix for x in nbrs(a) if x not in prefix
                              and label in by_atom[x].locants
                              and (ELEMENT_LOCANT.match(label) or not (
                                  part_of.get(x) is not None and part_of[x].kind == "substituent"
                                  and any(ELEMENT_LOCANT.match(loc) for loc in by_atom[x].locants)))}
                ok = ok and (lit - placed) <= reach
            elif chained and not attachment_written_inside(trace, key) and mol is not None:
                ring_attach = {a for a in seed if label in by_atom[a].locants
                               and mol.GetAtomWithIdx(a).IsInRing() and any(x not in seed for x in nbrs(a))
                               and not (label == "1" and all(by_atom[x].element == "C" for x in seed)
                                        and len([r for r in mol.GetRingInfo().AtomRings() if set(r) <= seed]) == 1)}
            leading = bool(ring_attach and at_front)
            if leading:
                ok = ok and lit - placed <= ring_attach
                chained = False
            if ok and chained:
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
