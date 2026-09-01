"""2D structure depiction helper.

mol_to_svg_data_uri is the live entry point, used by app.tasks (the naming
paths) and app.jobs_api (GET /api/depict). Callers hold an already-parsed
RDKit Mol by the time they need a picture, so there is no SMILES-string
variant -- there was one, depict_svg_data_uri, and it had no callers left.

Renders a molecule's 2D structure with RDKit's
rdMolDraw2D.MolDraw2DSVG, and packages the result as a self-contained
"data:image/svg+xml;base64,..." URI so the frontend can drop it straight
into an <img src> with no separate image-serving endpoint required.
"""

import base64

from rdkit import Chem
from rdkit.Chem.Draw import rdMolDraw2D

_WIDTH = 240
_HEIGHT = 180


def mol_to_svg_data_uri(mol: Chem.Mol) -> str:
    """Render an already-parsed RDKit Mol as a 240x180 2D SVG data URI."""
    drawer = rdMolDraw2D.MolDraw2DSVG(_WIDTH, _HEIGHT)
    drawer.DrawMolecule(mol)
    drawer.FinishDrawing()
    svg = drawer.GetDrawingText()
    encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"
