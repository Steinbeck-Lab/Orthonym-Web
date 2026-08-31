import pytest

from app.inputs import (
    InputFormat,
    ParsedMolecule,
    TooManyMolecules,
    parse,
    sniff,
)

ETHANOL_MOLBLOCK = """ethanol
  RDKit          2D

  3  2  0  0  0  0  0  0  0  0999 V2000
    0.0000    0.0000    0.0000 C   0  0
    1.2990    0.7500    0.0000 C   0  0
    2.5981    0.0000    0.0000 O   0  0
  1  2  1  0
  2  3  1  0
M  END
"""

BENZENE_MOLBLOCK = """benzene
  RDKit          2D

  6  6  0  0  0  0  0  0  0  0999 V2000
    1.5000    0.0000    0.0000 C   0  0
    0.7500    1.2990    0.0000 C   0  0
   -0.7500    1.2990    0.0000 C   0  0
   -1.5000    0.0000    0.0000 C   0  0
   -0.7500   -1.2990    0.0000 C   0  0
    0.7500   -1.2990    0.0000 C   0  0
  1  2  2  0
  2  3  1  0
  3  4  2  0
  4  5  1  0
  5  6  2  0
  6  1  1  0
M  END
"""


def _sdf(*molblocks: str) -> bytes:
    return "".join(mb + "$$$$\n" for mb in molblocks).encode("utf-8")


def test_sniff_multi_record_sdf():
    assert sniff(_sdf(ETHANOL_MOLBLOCK, BENZENE_MOLBLOCK)) is InputFormat.SDF


def test_sniff_single_molfile():
    # No $$$$ terminator, but a V2000 counts line -- a lone molfile, not SDF.
    assert sniff(ETHANOL_MOLBLOCK.encode()) is InputFormat.MOLFILE


def test_sniff_csv_with_header():
    assert sniff(b"smiles,id\nCCO,a\n") is InputFormat.CSV


def test_sniff_bare_smiles_header_is_still_csv():
    # A one-column CSV has no delimiter on the header line. Treating it as a
    # SMILES list would turn the word "smiles" into a molecule that fails.
    assert sniff(b"smiles\nCCO\n") is InputFormat.CSV


def test_sniff_plain_smiles_list():
    assert sniff(b"CCO\nc1ccccc1\n") is InputFormat.SMILES_LIST


def test_parse_sdf_keeps_titles_and_order():
    rows = parse(_sdf(ETHANOL_MOLBLOCK, BENZENE_MOLBLOCK), InputFormat.SDF, 100)
    assert [r.index for r in rows] == [0, 1]
    assert [r.input_id for r in rows] == ["ethanol", "benzene"]
    assert rows[0].smiles == "CCO"
    assert all(r.error is None for r in rows)


def test_parse_sdf_bad_record_becomes_an_error_row_not_an_abort():
    data = _sdf(ETHANOL_MOLBLOCK, "not a molblock at all\n", BENZENE_MOLBLOCK)
    rows = parse(data, InputFormat.SDF, 100)
    assert len(rows) == 3
    assert rows[0].smiles == "CCO"
    assert rows[1].smiles is None and rows[1].error
    assert rows[2].smiles == "c1ccccc1"


def test_parse_single_molfile():
    rows = parse(ETHANOL_MOLBLOCK.encode(), InputFormat.MOLFILE, 100)
    assert len(rows) == 1
    assert rows[0].smiles == "CCO"
    assert rows[0].input_id == "ethanol"


def test_parse_smiles_list_with_ids():
    rows = parse(b"CCO ethanol\nc1ccccc1\tbenzene\n", InputFormat.SMILES_LIST, 100)
    assert [r.smiles for r in rows] == ["CCO", "c1ccccc1"]
    assert [r.input_id for r in rows] == ["ethanol", "benzene"]


def test_parse_smiles_list_skips_blank_lines():
    rows = parse(b"CCO\n\n   \nc1ccccc1\n", InputFormat.SMILES_LIST, 100)
    assert [r.smiles for r in rows] == ["CCO", "c1ccccc1"]


def test_parse_smiles_list_records_unparseable_entry():
    rows = parse(b"CCO\nnot_a_smiles(((\n", InputFormat.SMILES_LIST, 100)
    assert rows[0].error is None
    assert rows[1].smiles is None and rows[1].error


def test_parse_csv_uses_id_column_for_input_id():
    rows = parse(b"smiles,id\nCCO,mol-1\nc1ccccc1,mol-2\n", InputFormat.CSV, 100)
    assert [r.input_id for r in rows] == ["mol-1", "mol-2"]


def test_parse_csv_without_smiles_column_raises():
    with pytest.raises(ValueError, match="smiles"):
        parse(b"structure,id\nCCO,a\n", InputFormat.CSV, 100)


def test_parse_stops_at_the_limit_rather_than_reading_the_whole_file():
    data = b"CCO\n" * 50
    with pytest.raises(TooManyMolecules) as excinfo:
        parse(data, InputFormat.SMILES_LIST, 10)
    assert excinfo.value.limit == 10


def test_parsed_molecule_keeps_the_raw_input_for_reporting():
    rows = parse(b"CCO ethanol\n", InputFormat.SMILES_LIST, 100)
    assert isinstance(rows[0], ParsedMolecule)
    assert rows[0].raw_input == "CCO ethanol"
