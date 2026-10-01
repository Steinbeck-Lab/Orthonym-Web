"""Explain: how an IUPAC name is written, piece by piece, and which atoms
each piece names. Spec: docs/superpowers/specs/2026-09-30-explain-opsin-
trace-design.md (gitignored).

* explain_name -- name in. OPSIN's own built structure IS the molecule, so
  the trace's atom indices are the drawing's.
* explain_molecule -- structure in. The engine names the molecule, the name
  is traced, and every node's atoms are remapped onto the USER's molecule by
  substructure match under the all-matches-agree rule. A node whose atoms
  cannot be agreed keeps its text and line and is flagged atoms_unmapped.
"""

import difflib
import logging
from typing import Optional

from celery.exceptions import SoftTimeLimitExceeded
from rdkit import Chem
from rdkit.Chem.Draw import rdMolDraw2D

from orthonym import Orthonym
from orthonym.errors import is_failure_name

from .explain_tree import build_nodes
from .opsin_trace import TraceFailure, trace

logger = logging.getLogger(__name__)

_EXPLAIN_WIDTH = 340
_EXPLAIN_HEIGHT = 260

# Generous headroom above any realistic small molecule's automorphism count;
# hitting it means "inconclusive", never "confirmed".
_MAX_SUBSTRUCT_MATCHES = 4096

_FAILURE_MESSAGES = {
    "unavailable": "Explain is not available on this server right now. Naming still works.",
    "unreadable": "OPSIN cannot read this name, so it cannot be explained.",
    "mismatch": "Could not explain this name.",
    "unplaced": "OPSIN reads this name in a reordered form (for example a CAS index name), "
                "so its parts cannot be matched to the text. Try the IUPAC form.",
}


_NOT_NAMED = ("Orthonym could not confidently name this molecule, so "
              "there is nothing to explain.")


def _inline_svg(mol: Chem.Mol) -> tuple[str, list[list[float]]]:
    """Raw SVG plus every atom's pixel coordinate from the SAME drawer, so the
    two cannot drift (RDKit draws no standalone element for most carbons)."""
    drawer = rdMolDraw2D.MolDraw2DSVG(_EXPLAIN_WIDTH, _EXPLAIN_HEIGHT)
    drawer.DrawMolecule(mol)
    drawer.FinishDrawing()
    points = []
    for index in range(mol.GetNumAtoms()):
        point = drawer.GetDrawCoords(index)
        points.append([float(point.x), float(point.y)])
    return drawer.GetDrawingText(), points


def _response(smiles, name, *, svg=None, atom_points=(), total_atoms=0, nodes=(), error=None) -> dict:
    return {
        "smiles": smiles, "name": name, "svg": svg, "atom_points": list(atom_points),
        "total_atoms": total_atoms, "nodes": list(nodes), "error": error,
    }


def _align_spans(nodes: list[dict], read_text: str, shown_text: str) -> list[dict]:
    """Spans index the text OPSIN read; the page shows the user's text. Map
    each position through a character alignment. A position inside a
    replaced block maps to the whole original block; a span that maps to
    nothing becomes None. The shown name is never rewritten."""
    if read_text == shown_text:
        return nodes
    matcher = difflib.SequenceMatcher(None, read_text, shown_text, autojunk=False)
    lo = [0] * len(read_text)
    hi = [0] * len(read_text)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        for i in range(i1, i2):
            if tag == "equal":
                lo[i], hi[i] = j1 + (i - i1), j1 + (i - i1) + 1
            else:
                lo[i], hi[i] = j1, j2
    out = []
    for node in nodes:
        span = node.get("span")
        if span:
            start, end = span
            new: Optional[list[int]] = None
            if 0 <= start < end <= len(read_text):
                a, b = lo[start], hi[end - 1]
                new = [a, b] if b > a else None
            node = {**node, "span": new}
        out.append(node)
    return out


def explain_name(name: str) -> dict:
    result = trace(name)
    if isinstance(result, TraceFailure):
        return _response("", name, error=_FAILURE_MESSAGES[result.reason])
    mol = Chem.MolFromSmiles(result.smiles)
    if mol is None:
        return _response(result.smiles, name,
                         error="OPSIN parsed this name but the structure could not be read.")
    try:
        nodes = _align_spans(build_nodes(result), result.text, name)
    except Exception:
        # A node-building defect must never become a 500 or blank the page
        # with no reason; it is logged loudly and reported as one message.
        logger.exception("explain: building nodes failed for %r", name)
        return _response(result.smiles, name, error=_FAILURE_MESSAGES["mismatch"])
    try:
        svg, atom_points = _inline_svg(mol)
    except SoftTimeLimitExceeded:
        raise
    except Exception:
        logger.exception("explain: drawing failed for %r", name)
        return _response(result.smiles, name, error=_FAILURE_MESSAGES["mismatch"])
    return _response(result.smiles, name, svg=svg, atom_points=atom_points,
                     total_atoms=mol.GetNumAtoms(), nodes=nodes)


def _agreed_atoms(indices, matches) -> Optional[frozenset]:
    """Maps `indices` (into OPSIN's re-parse) through EVERY substructure
    match; returns the image only if every match agrees on it. Symmetric
    groups (ibuprofen's isobutyl: "methyl" + "propyl" over two equivalent
    terminal carbons) disagree on the parts but agree on the union."""
    if not matches:
        return None
    sets = []
    for match in matches:
        if any(not 0 <= i < len(match) for i in indices):
            return None
        sets.append(frozenset(match[i] for i in indices))
    if any(s != sets[0] for s in sets):
        return None
    return sets[0]


def _remap_node(node: dict, matches) -> dict:
    owns = _agreed_atoms(node["owns"], matches) if node["owns"] else frozenset()
    lights = _agreed_atoms(node["lights"], matches) if node["lights"] else frozenset()
    if owns is None or lights is None:
        return {**node, "owns": [], "lights": [], "atoms_unmapped": True}
    return {**node, "owns": sorted(owns), "lights": sorted(lights)}


def explain_molecule(smiles: str, namer: Orthonym) -> dict:
    """Name `smiles` with the SAME primary namer /api/translate uses, trace
    that name, and remap every node onto the user's molecule. All returned
    atom indices refer to the Mol that `svg` draws."""
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return _response(smiles, None, error="Could not parse this SMILES string")
    # The spec (section 7) gives an engine that produced no name one message; an engine
    # that RAISES produced no name either, so it gets the same one, never a 500.
    try:
        name = namer.name_with_tree(smiles).name
    except SoftTimeLimitExceeded:
        raise
    except Exception:
        logger.exception("explain: the engine raised while naming %r", smiles)
        name = None
    if name is None or is_failure_name(name):
        return _response(smiles, None, total_atoms=mol.GetNumAtoms(), error=_NOT_NAMED)
    try:
        svg, atom_points = _inline_svg(mol)
    except SoftTimeLimitExceeded:
        raise
    except Exception:
        # No spec row covers a drawing defect; it is a defect in our own work on a
        # name that did parse, which section 7 reports as "Could not explain this name."
        logger.exception("explain: drawing failed for %r", smiles)
        return _response(smiles, name, total_atoms=mol.GetNumAtoms(),
                         error=_FAILURE_MESSAGES["mismatch"])
    total_atoms = mol.GetNumAtoms()
    named = explain_name(name)
    if named["error"] is not None:
        return _response(smiles, name, svg=svg, atom_points=atom_points,
                         total_atoms=total_atoms, error=named["error"])

    opsin_mol = Chem.MolFromSmiles(named["smiles"])
    matches: tuple = ()
    if opsin_mol is None:
        logger.warning("explain: OPSIN's SMILES for %r could not be re-read", name)
    elif opsin_mol.GetNumAtoms() != mol.GetNumAtoms():
        # A proper-substructure match would map happily while leaving the
        # user's extra atoms in no node at all: the name does not describe
        # this whole molecule, so no node is mapped.
        logger.warning("explain: %r re-parses to %d heavy atoms, molecule has %d",
                       name, opsin_mol.GetNumAtoms(), mol.GetNumAtoms())
    else:
        matches = mol.GetSubstructMatches(opsin_mol, uniquify=False,
                                          maxMatches=_MAX_SUBSTRUCT_MATCHES)
        if len(matches) >= _MAX_SUBSTRUCT_MATCHES:
            logger.warning("explain: match cap hit for %r -- inconclusive", name)
            matches = ()
    nodes = [_remap_node(node, matches) for node in named["nodes"]]
    return _response(smiles, name, svg=svg, atom_points=atom_points,
                     total_atoms=total_atoms, nodes=nodes)
