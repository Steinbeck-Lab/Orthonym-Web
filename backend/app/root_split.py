"""Splits a root part's atoms into the parent skeleton and the principal
characteristic group's own atoms.

This comes from OPSIN's own locants, not the parse tree (a <suffix> element
carries an EMPTY fragment; its atoms are merged into the group's). OPSIN
gives a skeleton atom a numeric locant (caffeine's N1 is ['1','N'], C2 is
['2']) and a suffix atom only an element-symbol locant (the carbonyl oxygens
are ['O'] and ["O'"]). If the split looks unsafe, everything stays parent:
degrade, never guess.
"""

from __future__ import annotations

from typing import NamedTuple, Sequence

from rdkit import Chem

from .opsin_trace import Trace


class RootSplit(NamedTuple):
    parent_atoms: tuple[int, ...]
    suffix_atoms: tuple[int, ...]
    suffix_locants: dict[int, str]


def _has_numeric_locant(locants) -> bool:
    return any(locant and locant[0].isdigit() for locant in locants)


def split_root(trace: Trace, atoms: Sequence[int]) -> RootSplit:
    by_index = {atom.index: atom for atom in trace.atoms}
    indices = sorted(atoms)
    parent = [i for i in indices if _has_numeric_locant(by_index[i].locants)]
    suffix = [i for i in indices if not _has_numeric_locant(by_index[i].locants)]

    # A root with no numeric locants at all (some retained names) would put
    # every atom in `suffix`, which is meaningless. Keep it whole.
    if not parent:
        return RootSplit(tuple(indices), (), {})
    mol = Chem.MolFromSmiles(trace.smiles)
    if mol is None:
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
