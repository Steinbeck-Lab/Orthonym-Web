"""Opt-in salt stripping: keep the largest organic fragment of a SMILES.

Off unless the visitor turns it on. The engine then names the kept fragment
exactly as if it had been typed alone, and the row says what was removed, so
a stripped row never looks as if the original was named.
"""

from collections import Counter

from rdkit import Chem, rdBase
from rdkit.Chem.MolStandardize import rdMolStandardize

_CHOOSER = rdMolStandardize.LargestFragmentChooser(preferOrganic=True)


def _canonical(smiles: str) -> str | None:
    with rdBase.BlockLogs():
        mol = Chem.MolFromSmiles(smiles)
    return Chem.MolToSmiles(mol) if mol is not None else None


def strip(smiles: str) -> tuple[str, dict]:
    """(SMILES to name, the row's notes) for a stripping request.

    Notes are {} (one fragment: nothing to strip), {"stripped_from",
    "removed"} (fragments taken off), or {"strip_skipped": True} (RDKit cannot
    read the structure -- a CDK-only input -- so nothing could be stripped and
    the row must say so). One RDKit parse decides all three.

    The kept fragment is the TYPED text whenever it can be found (the owner
    rule: name the SMILES the visitor typed; the engine is not invariant to
    atom order).
    """
    with rdBase.BlockLogs():
        mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return smiles, ({"strip_skipped": True} if "." in smiles else {})
    fragments = Chem.GetMolFrags(mol, asMols=True)
    if len(fragments) < 2:
        return smiles, {}
    chosen = Chem.MolToSmiles(_CHOOSER.choose(mol))

    pieces = smiles.split(".")
    canon = [_canonical(piece) for piece in pieces]
    if None not in canon and Counter(canon) == Counter(Chem.MolToSmiles(f) for f in fragments):
        at = canon.index(chosen)
        kept, removed = pieces[at], ".".join(pieces[:at] + pieces[at + 1:])
    else:
        # ponytail: a ring-closure digit spans a dot, so the typed pieces are
        # not the fragments; name RDKit's canonical form of the kept fragment.
        others = [Chem.MolToSmiles(f) for f in fragments]
        others.remove(chosen)
        kept, removed = chosen, ".".join(others)
    return kept, {"stripped_from": smiles, "removed": removed}


def strip_salts(smiles: str) -> tuple[str, str | None]:
    """(kept, removed); `removed` is None when nothing was stripped."""
    kept, notes = strip(smiles)
    return kept, notes.get("removed")
