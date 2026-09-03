"""2D structure depiction: CDK first, RDKit as the safety net.

`structure_svg_data_uri` is the one entry point, used by app.orthonym_service
and app.tasks (the naming paths) and app.jobs_api (GET /api/depict). It packages
the result as a self-contained "data:image/svg+xml;base64,..." URI so the
frontend can drop it straight into an <img src> with no image-serving endpoint.

WHY TWO ENGINES
---------------
CDK is the DEFAULT because it draws the stereochemistry: its depiction generator
carries CIP descriptors -- (R)/(S) on tetrahedral centres, (E)/(Z) on double
bonds, and "(?)" on a centre that is a real stereocentre but undefined in the
input. That last one matters here more than anywhere: a site whose whole point
is not overstating what it knows should not silently draw an undefined centre as
though it were settled. RDKit's default drawing says none of this.

RDKit remains the fallback for one structural reason, not as belt and braces:
CDK lives in the JVM, and a JVM is not guaranteed. `cdk_bridge` BOOTS one
lazily in whatever process asks -- including the web process, which is why
GET /api/depict serves CDK too (see jobs_api.depict, which documents the cost)
-- but it can still come back empty: a build with the jar stripped, a JVM that
will not start, an image without a JRE. In any of those a picture drawn by
RDKit is the right answer and a blank card is not.

Note what this does NOT change: jvm_guard still refuses every NAMING endpoint
unless a WORKER reports a live JVM. A JVM in the web process draws pictures; it
does not make the web process able to name anything.

The engines are asked in the order (CDK, RDKit) and the FIRST that answers wins,
so a molecule never silently changes renderer between two requests unless the
JVM's availability itself changed.
"""

from __future__ import annotations

import base64
from typing import Optional

from rdkit import Chem
from rdkit.Chem.Draw import rdMolDraw2D

from app import cdk_bridge

_WIDTH = 240
_HEIGHT = 180


def _rdkit_svg(mol: Chem.Mol) -> str:
    """Render an already-parsed RDKit Mol as a 240x180 2D SVG."""
    drawer = rdMolDraw2D.MolDraw2DSVG(_WIDTH, _HEIGHT)
    drawer.DrawMolecule(mol)
    drawer.FinishDrawing()
    return drawer.GetDrawingText()


def structure_svg_data_uri(smiles: Optional[str], mol: Optional[Chem.Mol] = None) -> Optional[str]:
    """A 240x180 structure picture as a base64 SVG data URI, or None.

    `smiles` drives the CDK path and `mol` the RDKit one; a caller that holds
    both should pass both. Passing only `mol` gives up the CIP labels, because
    CDK is asked for a picture by string.

    Returns None when neither engine can draw the molecule -- which is a real
    state, not an error: CDK is absent in any process without a JVM, and `mol`
    is None for a SMILES RDKit refused.
    """
    if smiles:
        svg = cdk_bridge.depict_svg(smiles, width=_WIDTH, height=_HEIGHT)
        if svg:
            return _as_data_uri(svg)

    if mol is not None:
        return _as_data_uri(_rdkit_svg(mol))

    return None


def _as_data_uri(svg: str) -> str:
    encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"
