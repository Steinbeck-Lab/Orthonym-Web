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
from typing import NamedTuple, Optional, Sequence

from rdkit import Chem

from .label_rules import ELEMENT_LOCANT
from .opsin_trace import Trace


class RootSplit(NamedTuple):
    parent_atoms: tuple[int, ...]
    suffix_atoms: tuple[int, ...]
    suffix_locants: dict[int, str]


def _has_numeric_locant(locants) -> bool:
    return any(locant and locant[0].isdigit() for locant in locants)


def _has_element_locant(locants) -> bool:
    """"O", "O'", "N", "Cl": a capitalised element symbol, optionally primed.
    Not numeric, not Greek ("alpha", "omega")."""
    return any(ELEMENT_LOCANT.match(locant or "") for locant in locants)


_DIGITS = re.compile(r"\d+(?:[a-z](?![a-z]))?'*")
_LOCANT_LIKE = ("locant", "colonOrSemiColonDelimitedLocant", "stereoChemistry")
_SKIPPED = ("multiplier", "hyphen", "ine", "e", "infix", "suffixPrefix")


def _group_locants(trace: Trace, indices) -> set[str]:
    """The numeric locants the principal characteristic group sits on: the
    locant list written right before each suffix ("2,6-dione", "3,17beta-diol"),
    else position 1 (an unlocanted acid, amide, ester or alcohol ending)."""
    root = next((p for p in trace.parts if p.kind == "root" and set(indices) == set(p.atoms)), None)
    found: set[str] = set()
    counted = False
    if root is not None and root.span is not None:
        for tok in trace.tokens:
            if tok.kind != "suffix" or tok.owner != root.span:
                continue
            j = tok.index - 1
            while j >= 0 and trace.tokens[j].kind in _SKIPPED:
                counted = counted or trace.tokens[j].kind == "multiplier"
                j -= 1
            if j >= 0 and trace.tokens[j].kind in _LOCANT_LIKE:
                text = trace.text[trace.tokens[j].span[0]:trace.tokens[j].span[1]]
                for item in re.sub(r"\([^)]*\)", "", text).split(","):
                    m = _DIGITS.match(item.strip("-() "))
                    if m:
                        found.add(m.group(0).rstrip("'"))
    if found:
        return found
    # No locant written. "hexanedioic acid", "pentanedial": the counted group
    # sits on both ends of the chain.
    ends = {"1"}
    if counted:
        numeric = [int(m.group(0)) for a in indices for loc in trace.atoms[a].locants
                   if (m := re.match(r"\d+$", loc))]
        if numeric:
            ends.add(str(max(numeric)))
    return ends


def split_root(trace: Trace, atoms: Sequence[int], mol: Optional[Chem.Mol] = None) -> RootSplit:
    """`mol` is the parsed traced SMILES when the caller already holds it."""
    by_index = {atom.index: atom for atom in trace.atoms}
    indices = sorted(atoms)
    if mol is None:
        mol = Chem.MolFromSmiles(trace.smiles)
    if mol is None:
        return RootSplit(tuple(indices), (), {})
    pool = set(indices)

    def neighbours(i):
        return [n.GetIdx() for n in mol.GetAtomWithIdx(i).GetNeighbors() if n.GetIdx() in pool]

    def hetero_of(i):
        return [n for n in neighbours(i) if by_index[n].element not in ("C", "H")]

    # Candidate group heteroatoms: an element-symbol locant and no numeric one
    # ("O", "O'", "N"), or no locant at all. Whether one IS the group's is
    # decided by where it sits, never by its locant alone: OPSIN gives a
    # serine side-chain O, a cysteine S or an amino-acid alpha N the same kind
    # of locant as an amide's.
    # Hydrogen is never a characteristic-group atom: an isotopic hydrogen ("(2H3)methanol")
    # belongs to the skeleton it is bonded to.
    candidates = {i for i in indices if by_index[i].element not in ("C", "H")
                  and not _has_numeric_locant(by_index[i].locants)
                  and (_has_element_locant(by_index[i].locants) or not by_index[i].locants)}
    numbered = _group_locants(trace, indices)

    def on_group_carbon(carbon):
        """A carboxyl/amide/ester carbon (two heteroatoms), the carbon of a
        locanted one-heteroatom group ("2,6-dione", "propan-2-ol"), or a
        carbon with no numeric locant joined to the skeleton that carries a
        candidate (benzoic acid's and benzonitrile's carbon)."""
        near = [n for n in hetero_of(carbon) if n in candidates or not _has_numeric_locant(by_index[n].locants)]
        locants = by_index[carbon].locants
        # Two heteroatoms on one carbon make a group carbon only when it is
        # the one the suffix names: a carbon with no numeric locant, one on a
        # written suffix locant, or one on a plainly numbered skeleton
        # ("citric acid": 1, 5). An amino-acid stem numbers its side chain
        # with Greek letters too (asparagine's C4 is 4/gamma, arginine's
        # guanidine carbon is guanidino-C/99): that carboxamide or guanidine is
        # the stem's, not the ending's.
        # "Plain": digits, or a bare element symbol beside them (oxalic acid's
        # second carbon is 2/C). A Greek letter or a compound symbol marks a stem.
        plain = all(re.match(r"^(\d+|[A-Z][a-z]?)'*$", loc) for loc in locants)
        if len(near) >= 2 and (not _has_numeric_locant(locants) or plain
                               or any(loc.rstrip("'") in numbered for loc in locants)):
            return True
        if any(loc.rstrip("'") in numbered for loc in locants) and near:
            return True
        # benzoic acid's and benzonitrile's carbon: joined to the skeleton by a
        # carbon that is not itself the ending. A stem's alpha carbon (methyl
        # phenylalaninate: alpha, with the amino N beside it) is joined to the
        # ester's own carboxyl carbon, so the ending is next door, not here.
        return (not _has_numeric_locant(locants) and any(_has_element_locant(by_index[n].locants) for n in near)
                and any(by_index[n].element == "C" for n in neighbours(carbon))
                and not any(by_index[n].element == "C" and len(hetero_of(n)) >= 2 for n in neighbours(carbon)))

    hetero = {i for i in candidates
              if any(by_index[n].element == "C" and on_group_carbon(n) for n in neighbours(i))}
    # A sulfonyl or phosphoryl centre (sulfonic acid, sulfonamide, phosphonate)
    # is the group itself wherever it is bonded: S or P with two or more
    # heteroatoms on it.
    hetero |= {i for i in candidates if by_index[i].element in ("S", "P")
               and len([n for n in hetero_of(i) if n in candidates]) >= 2}
    # Heteroatoms bonded to an accepted one belong to the same group
    # (the oxygens of S(=O)(=O)O, the second N of a diazonium).
    grown = True
    while grown:
        more = {i for i in candidates if i not in hetero and any(n in hetero for n in neighbours(i))}
        hetero |= more
        grown = bool(more)
    # The group's own carbon has no numeric locant (benzoic acid's carboxyl C,
    # benzonitrile's C). A skeleton carbon with only a Greek locant
    # (phenylalanine's alpha and beta) is not joined to two group atoms.
    carbons = {i for i in indices if by_index[i].element == "C"
               and not _has_numeric_locant(by_index[i].locants)
               and any(n in hetero for n in neighbours(i)) and on_group_carbon(i)}
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
