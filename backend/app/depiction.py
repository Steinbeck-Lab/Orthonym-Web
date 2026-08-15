"""2D structure depiction helper, shared by /api/translate and
/api/iupac-to-smiles.

Renders a molecule's 2D structure from a SMILES string with RDKit's
rdMolDraw2D.MolDraw2DSVG, and packages the result as a self-contained
"data:image/svg+xml;base64,..." URI so the frontend can drop it straight
into an <img src> with no separate image-serving endpoint required.
"""

import base64
from typing import Optional

from rdkit import Chem
from rdkit.Chem.Draw import rdMolDraw2D

_WIDTH = 240
_HEIGHT = 180


def depict_svg_data_uri(smiles: str) -> Optional[str]:
    """Render `smiles` as a 240x180 2D SVG, returned as a data: URI.

    Returns None if `smiles` cannot be parsed by RDKit.
    """
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    return mol_to_svg_data_uri(mol)


def mol_to_svg_data_uri(mol: Chem.Mol) -> str:
    """Render an already-parsed RDKit Mol as a 240x180 2D SVG data URI."""
    drawer = rdMolDraw2D.MolDraw2DSVG(_WIDTH, _HEIGHT)
    drawer.DrawMolecule(mol)
    drawer.FinishDrawing()
    svg = drawer.GetDrawingText()
    encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"
