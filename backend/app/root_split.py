"""Splits OPSIN's `root` part into the parent skeleton and the principal
characteristic group's own atoms.

This cannot come from the parse tree: verified, OPSIN's <suffix> elements
carry an EMPTY fragment and their atoms are merged into the parent group's
fragment. It comes from locants instead. OPSIN gives a skeleton atom a
numeric locant (caffeine's N1 is ['1','N'], C2 is ['2']) and gives a suffix
atom only an element-symbol locant (the carbonyl oxygens are ['O'] and
["O'"]). That distinction is OPSIN's own labelling, not a guess about the
name string.

If the split looks unsafe for a given name, `split_root` returns everything
as parent with no suffix -- degrade, never guess (see spec section 6).
"""

from __future__ import annotations

from typing import NamedTuple

from rdkit import Chem

from .opsin_decompose import Decomposition, NamePart, heavy_atom_indices


class RootSplit(NamedTuple):
    parent_atoms: tuple[int, ...]
    suffix_atoms: tuple[int, ...]
    suffix_locants: dict[int, str]


def _has_numeric_locant(locants) -> bool:
    return any(locant and locant[0].isdigit() for locant in locants)


def split_root(result: Decomposition, root: NamePart) -> RootSplit:
    indices = heavy_atom_indices(result, root.opsin_atom_ids)
    by_index = {atom.rdkit_index: atom for atom in result.atoms}

    parent, suffix = [], []
    for index in indices:
        if _has_numeric_locant(by_index[index].locants):
            parent.append(index)
        else:
            suffix.append(index)

    # Safety net: a root with no numeric locants at all (some retained names)
    # would put every atom in `suffix`, which is meaningless. Keep it whole.
    if not parent:
        return RootSplit(tuple(indices), (), {})

    mol = Chem.MolFromSmiles(result.smiles)
    if mol is None:
        return RootSplit(tuple(indices), (), {})

    parent_set = set(parent)
    suffix_locants: dict[int, str] = {}
    for index in suffix:
        for neighbor in mol.GetAtomWithIdx(index).GetNeighbors():
            if neighbor.GetIdx() in parent_set:
                numeric = [
                    locant
                    for locant in by_index[neighbor.GetIdx()].locants
                    if locant and locant[0].isdigit()
                ]
                if numeric:
                    suffix_locants[index] = numeric[0]
                break

    return RootSplit(tuple(parent), tuple(suffix), suffix_locants)
