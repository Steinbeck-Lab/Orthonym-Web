"""A finished batch job as SDF: one record per row, never fewer.

The molblock is rebuilt from the row's SMILES (2D coordinates); an uploaded
molfile's own coordinates are not stored per row, so they cannot be kept. A
row RDKit cannot read -- or one with no SMILES at all, a parse error -- is
still written, as an empty molblock with its tags, so the file has exactly as
many records as the job has rows and the reason travels with it.
"""

from rdkit import Chem
from rdkit.Chem import rdDepictor

# (SD tag, row key), in file order.
SDF_TAGS: list[tuple[str, str]] = [
    ("ORTHONYM_NAME", "name"),
    ("ORTHONYM_STATUS", "status"),
    ("ORTHONYM_TIER", "tier"),
    ("ORTHONYM_LIMIT_CODE", "limit_code"),
    ("ROUNDTRIP_SMILES", "roundtrip_smiles"),
    ("ROUNDTRIP_MATCH", "roundtrip_match"),
    ("INPUT", "input"),
    ("INPUT_ID", "input_id"),
    ("ERROR", "error"),
    ("ENGINE_VERSION", "engine_version"),
    ("ENGINE_COMMIT", "engine_commit"),
]


def _value(value) -> str:
    """One line, always. A blank line ends an SD data block, so a newline in
    a pasted input or a multi-line error would corrupt every later record."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    text = " ".join(str(value).split())
    # A line of "$$$$" ends a record and one starting ">" opens a tag, and
    # input, input_id and error are user text: a leading space keeps such a
    # value data. The cost is one leading space on such a value.
    return " " + text if text.startswith(("$$$$", ">")) else text


def _molblock(smiles: str | None, title: str) -> str:
    mol = Chem.MolFromSmiles(smiles) if smiles else None
    if mol is None:
        mol = Chem.Mol()
    else:
        rdDepictor.Compute2DCoords(mol)
    mol.SetProp("_Name", title)
    return Chem.MolToMolBlock(mol)


def sdf_record(row: dict) -> str:
    """One SD record for a batch row, ending in `$$$$\\n`."""
    parts = [_molblock(row.get("smiles"), _value(row.get("input_id")))]
    for tag, key in SDF_TAGS:
        parts.append(f"> <{tag}>\n{_value(row.get(key))}\n\n")
    parts.append("$$$$\n")
    return "".join(parts)
