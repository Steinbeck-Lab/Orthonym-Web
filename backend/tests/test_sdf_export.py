"""The batch SDF export: one record per row, every row, tags intact."""

from rdkit import Chem

from app.sdf_export import sdf_record


def _row(**overrides):
    row = {
        "index": 0,
        "input": "CCO",
        "input_id": None,
        "smiles": "CCO",
        "name": "ethanol",
        "status": "pin",
        "tier": "pin_verified",
        "roundtrip_smiles": "CCO",
        "roundtrip_match": True,
        "formula": None,
        "limit_code": None,
        "error": None,
        "engine_version": "1.0.9",
        "engine_commit": "81ba930",
    }
    row.update(overrides)
    return row


def _read_all(text, tmp_path):
    path = tmp_path / "out.sdf"
    path.write_text(text)
    return list(Chem.SDMolSupplier(str(path), sanitize=False, removeHs=False))


def test_a_named_row_has_a_molblock_and_every_tag():
    record = sdf_record(_row())
    assert "> <ORTHONYM_NAME>\nethanol\n" in record
    assert "> <ORTHONYM_TIER>\npin_verified\n" in record
    assert "> <ROUNDTRIP_MATCH>\ntrue\n" in record
    assert record.endswith("$$$$\n")
    mol = Chem.MolFromMolBlock(record.split("> <")[0])
    assert mol.GetNumHeavyAtoms() == 3


def test_a_row_without_smiles_is_still_a_record(tmp_path):
    record = sdf_record(_row(smiles=None, name=None, status="error", error="bad"))
    (mol,) = _read_all(record, tmp_path)
    # RDKit reads an empty molblock as a 0-atom Mol, not as None: the record
    # survives, so the file keeps one record per row.
    assert mol is not None and mol.GetNumAtoms() == 0
    assert mol.GetProp("ERROR") == "bad"


def test_a_newline_in_a_value_cannot_end_the_block(tmp_path):
    record = sdf_record(_row(error="line one\n\nline two", input="a\r\nb"))
    (mol,) = _read_all(record, tmp_path)
    assert mol.GetProp("ERROR") == "line one line two"
    assert mol.GetProp("INPUT") == "a b"


def test_a_row_without_tier_writes_an_empty_tag():
    row = _row()
    del row["tier"]
    assert "> <ORTHONYM_TIER>\n\n" in sdf_record(row)


def test_records_round_trip_through_rdkit(tmp_path):
    text = "".join(
        [
            sdf_record(_row()),
            sdf_record(_row(index=1, smiles=None, name=None, status="error", error="x")),
            sdf_record(_row(index=2, smiles="c1ccccc1", name="benzene", status="fallback")),
        ]
    )
    mols = _read_all(text, tmp_path)
    assert [m.GetProp("ORTHONYM_STATUS") for m in mols] == ["pin", "error", "fallback"]


def test_the_title_line_is_the_input_id():
    record = sdf_record(_row(input_id="CPD-7"))
    assert record.split("\n", 1)[0] == "CPD-7"
