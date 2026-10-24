"""A finished batch job as SDF: one record per row, never fewer.

The molblock is rebuilt from the row's SMILES (2D coordinates); an uploaded
molfile's own coordinates are not stored per row, so they cannot be kept. A
row RDKit cannot read -- or one with no SMILES at all, a parse error -- is
still written, as an empty molblock with its tags, so the file has exactly as
many records as the job has rows and the reason travels with it.
"""

from rdkit import Chem
from rdkit.Chem import rdDepictor

from app.schemas import EXPORT_FIELDS

# SD tag names where they are not just the field in capitals: the engine's
# own verdict fields carry the ORTHONYM_ prefix.
_SD_NAME = {
    "name": "ORTHONYM_NAME",
    "status": "ORTHONYM_STATUS",
    "tier": "ORTHONYM_TIER",
    "limit_code": "ORTHONYM_LIMIT_CODE",
}

# (SD tag, row key), in file order: EXPORT_FIELDS minus the index and the
# SMILES, which the molblock itself carries.
SDF_TAGS: list[tuple[str, str]] = [
    (_SD_NAME.get(key, key.upper()), key)
    for key in EXPORT_FIELDS
    if key not in ("index", "smiles")
]


def _value(value) -> str:
    """One line, always. A blank line ends an SD data block, so a newline in
    a pasted input or a multi-line error would corrupt every later record.
    Only line breaks are folded: spaces and tabs inside a line are data."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    text = " ".join(line for line in str(value).splitlines() if line.strip())
    # A line of "$$$$" ends a record and one starting ">" opens a tag, and
    # input, input_id and error are user text: a leading space keeps such a
    # value data. The cost is one leading space on such a value.
    return " " + text if text.startswith(("$$$$", ">")) else text


def molblock_2d(mol) -> str:
    """A 2D V2000 molblock. Coordinates are computed on a COPY:
    Compute2DCoords mutates the molecule it is given, and a caller may still
    draw from it. Shared with /from-name's SDF (tasks.name_to_smiles)."""
    copy = Chem.Mol(mol)
    rdDepictor.Compute2DCoords(copy)
    return Chem.MolToMolBlock(copy)


def _molblock(smiles: str | None, title: str) -> str:
    mol = Chem.MolFromSmiles(smiles) if smiles else None
    if mol is None:
        mol = Chem.Mol()
    mol.SetProp("_Name", title)
    return molblock_2d(mol)


def sdf_record(row: dict) -> str:
    """One SD record for a batch row, ending in `$$$$\\n`."""
    parts = [_molblock(row.get("smiles"), _value(row.get("input_id")))]
    for tag, key in SDF_TAGS:
        parts.append(f"> <{tag}>\n{_value(row.get(key))}\n\n")
    parts.append("$$$$\n")
    return "".join(parts)
