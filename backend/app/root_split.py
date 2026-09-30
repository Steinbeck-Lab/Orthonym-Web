"""Splits a root part's atoms into the parent skeleton and the principal
characteristic group's own atoms.

This comes from OPSIN's own locants, not the parse tree (a <suffix> element
carries an EMPTY fragment; its atoms are merged into the group's). OPSIN
gives a skeleton atom a numeric locant (caffeine's N1 is ['1','N'], C2 is
['2']) and a suffix atom only an element-symbol locant (the carbonyl oxygens
are ['O'] and ["O'"]); the group's own carbon has no numeric locant and sits
on those heteroatoms. A heteroatom with NO locant (glycine's alpha nitrogen,
lactic acid's 2-hydroxyl oxygen) or a carbon with only a Greek locant
(phenylalanine's alpha and beta carbons) is skeleton. If the split looks unsafe, everything stays
parent: degrade, never guess.

Known limitation (pinned by a test, not fixed): conjunctive names such as
"cyclohexaneethanol" or "benzeneacetic acid" write a ring and a chain into
one root, and the chain carries its own element/numeric locants, so the split
can still hand chain atoms to the suffix.
"""

from __future__ import annotations

import re
from typing import NamedTuple, Sequence

from rdkit import Chem

from .opsin_trace import Trace


_ELEMENT_LOCANT = re.compile(r"^[A-Z][a-z]?'*$")


class RootSplit(NamedTuple):
    parent_atoms: tuple[int, ...]
    suffix_atoms: tuple[int, ...]
    suffix_locants: dict[int, str]


def _has_numeric_locant(locants) -> bool:
    return any(locant and locant[0].isdigit() for locant in locants)


def _has_element_locant(locants) -> bool:
    """"O", "O'", "N", "Cl": a capitalised element symbol, optionally primed.
    Not numeric, not Greek ("alpha", "omega")."""
    return any(_ELEMENT_LOCANT.match(locant or "") for locant in locants)


def _acid_like_suffix(trace: Trace, indices) -> bool:
    root = next((p for p in trace.parts if p.kind == "root" and set(indices) == set(p.atoms)), None)
    if root is None or root.span is None:
        return False
    texts = [trace.text[t.span[0]:t.span[1]].lower() for t in trace.tokens
             if t.kind == "suffix" and t.owner == root.span]
    return bool(texts) and all(x.endswith(("ate", "acid")) for x in texts)


def split_root(trace: Trace, atoms: Sequence[int]) -> RootSplit:
    by_index = {atom.index: atom for atom in trace.atoms}
    indices = sorted(atoms)
    mol = Chem.MolFromSmiles(trace.smiles)
    if mol is None:
        return RootSplit(tuple(indices), (), {})
    # An acid or ester ending ("ate", "oic acid") holds only oxygens. A
    # nitrogen OPSIN locates as "N" there belongs to an amino-acid stem's own
    # ending ("alan|in|ate"), so it is skeleton.
    acidic = _acid_like_suffix(trace, indices)
    hetero = {i for i in indices if _has_element_locant(by_index[i].locants)
              and not _has_numeric_locant(by_index[i].locants)
              and not (acidic and by_index[i].element == "N")}
    # A heteroatom with no locant at all is the group's own only when it sits
    # on the same carbon as one that has an element locant (an anhydride's
    # bridging O); glycine's alpha nitrogen and lactic acid's 2-hydroxyl do not.
    hetero |= {i for i in indices if i not in hetero and not by_index[i].locants
               and by_index[i].element != "C"
               and any(any(m.GetIdx() in hetero for m in n.GetNeighbors())
                       for n in mol.GetAtomWithIdx(i).GetNeighbors() if n.GetSymbol() == "C")}
    # The group's own carbon (benzoic acid's carboxyl C, benzonitrile's C) has
    # no numeric locant and sits on the group's heteroatoms. A skeleton atom
    # with only a Greek locant (phenylalanine's alpha and beta carbons) does
    # not sit on one, so it stays parent.
    carbons = {i for i in indices if i not in hetero and not _has_numeric_locant(by_index[i].locants)
               and by_index[i].element == "C"
               and any(n.GetIdx() in hetero for n in mol.GetAtomWithIdx(i).GetNeighbors())}
    suffix = sorted(hetero | carbons)
    suffix_set = set(suffix)
    parent = [i for i in indices if i not in suffix_set]

    # A root whose atoms ALL look like group atoms (some retained names) would
    # leave no skeleton, which is meaningless. Keep it whole.
    if not any(_has_numeric_locant(by_index[i].locants) for i in parent):
        return RootSplit(tuple(indices), (), {})
    parent_set = set(parent)
    suffix_locants: dict[int, str] = {}
    for index in suffix:
        for neighbor in mol.GetAtomWithIdx(index).GetNeighbors():
            if neighbor.GetIdx() in parent_set:
                numeric = [loc for loc in by_index[neighbor.GetIdx()].locants
                           if loc and loc[0].isdigit()]
                if numeric:
                    suffix_locants[index] = numeric[0]
                break
    return RootSplit(tuple(parent), tuple(suffix), suffix_locants)
