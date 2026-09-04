import pytest

from app.inputs import (
    InputFormat,
    ParsedMolecule,
    TooManyMolecules,
    count_molecules,
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


def test_parse_sdf_stops_sanitising_records_once_it_is_over_the_limit():
    """TEST-4: this used to be named "...rather than reading the whole file",
    which is not what the code does and never was.

    _parse_sdf calls SDMolSupplier.SetData(_decode(data)) and then
    len(supplier) -- both of which need the whole blob in memory and parsed
    before the first limit check can run. The property that IS real, and is
    the one worth protecting, is that the EXPENSIVE per-record work
    (supplier[index], which sanitises the molecule) stops at the limit. What
    bounds the blob itself is the byte cap in jobs_api._read_input, not this.

    Naming the untrue property was the actual risk: the next reader assumes
    an oversized upload is rejected without being fully read, and sizes
    something else on that assumption.
    """
    data = _sdf(ETHANOL_MOLBLOCK, BENZENE_MOLBLOCK, ETHANOL_MOLBLOCK)
    with pytest.raises(TooManyMolecules) as excinfo:
        parse(data, InputFormat.SDF, 2)
    assert excinfo.value.limit == 2
    # The raise happens at index 2 (2 >= 2), BEFORE supplier[2] is touched,
    # so exactly `limit` records were sanitised. A check loosened to `>`, or
    # moved after the supplier[index] access, sanitises one record too many.
    assert len(excinfo.value.partial) == 2


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


def test_parse_stops_rdkit_parsing_lines_once_it_is_over_the_limit():
    """TEST-4, the SMILES-list half. Same correction: _parse_smiles_list does
    `_decode(data).splitlines()`, which materialises every line in the input
    before the loop starts, so nothing here avoids reading the file.

    What it does avoid is the per-line RDKit work -- the MolFromSmiles
    parse -- which is the part that actually costs, and which is
    bounded to `limit` calls.
    """
    data = b"CCO\n" * 50
    with pytest.raises(TooManyMolecules) as excinfo:
        parse(data, InputFormat.SMILES_LIST, 10)
    assert excinfo.value.limit == 10
    assert len(excinfo.value.partial) == 10, (
        "more lines were RDKit-parsed than the limit allows"
    )


def test_parsed_molecule_keeps_the_raw_input_for_reporting():
    rows = parse(b"CCO ethanol\n", InputFormat.SMILES_LIST, 100)
    assert isinstance(rows[0], ParsedMolecule)
    assert rows[0].raw_input == "CCO ethanol"


def test_count_molecules_matches_parse_for_a_terminated_sdf():
    data = _sdf(ETHANOL_MOLBLOCK, BENZENE_MOLBLOCK, ETHANOL_MOLBLOCK)
    assert count_molecules(data, InputFormat.SDF) == len(
        parse(data, InputFormat.SDF, 100)
    )


def test_count_molecules_matches_parse_for_an_unterminated_final_sdf_record():
    """Round 4 review: Chem.SDMolSupplier treats end-of-file as an implicit
    terminator for the final record, so a 3-record SDF missing its LAST
    "$$$$" still parses as 3 -- a bare `.count("$$$$")` would answer 2 and
    undercount by exactly one, which is the bug this test exists to catch.
    """
    terminated = _sdf(ETHANOL_MOLBLOCK, BENZENE_MOLBLOCK, ETHANOL_MOLBLOCK)
    data = terminated[: terminated.rindex(b"$$$$")]
    assert count_molecules(data, InputFormat.SDF) == len(
        parse(data, InputFormat.SDF, 100)
    )


def test_count_molecules_matches_parse_for_an_sdf_with_no_terminator_at_all():
    # No "$$$$" anywhere -- one unterminated record, not zero.
    data = ETHANOL_MOLBLOCK.encode("utf-8")
    assert count_molecules(data, InputFormat.SDF) == len(
        parse(data, InputFormat.SDF, 100)
    )
    assert count_molecules(data, InputFormat.SDF) == 1


def test_count_molecules_matches_parse_for_a_csv():
    data = ("smiles,id\n" + "\n".join(f"CCO,m{i}" for i in range(11))).encode(
        "utf-8"
    )
    assert count_molecules(data, InputFormat.CSV) == len(
        parse(data, InputFormat.CSV, 100)
    )


def test_count_molecules_matches_parse_for_a_smiles_list():
    data = "\n".join(["CCO"] * 13).encode("utf-8")
    assert count_molecules(data, InputFormat.SMILES_LIST) == len(
        parse(data, InputFormat.SMILES_LIST, 100)
    )


def test_count_molecules_matches_parse_for_an_sdf_with_dollars_mid_line_in_a_data_field():
    """Round 5 review: SDMolSupplier only treats "$$$$" as a terminator
    when it STARTS a line, so a bare substring count over-counts an SD
    data field whose VALUE happens to contain the literal string mid-line
    -- confirmed live: RDKit reads this as one record (the field's "Price:
    $$$$ per unit" line is not a terminator; only the trailing "$$$$" that
    actually opens its own line is), while a naive `.count("$$$$")` would
    answer two.
    """
    data = (
        ETHANOL_MOLBLOCK + "> <Note>\nPrice: $$$$ per unit\n\n$$$$\n"
    ).encode("utf-8")
    assert count_molecules(data, InputFormat.SDF) == len(
        parse(data, InputFormat.SDF, 100)
    )
    assert count_molecules(data, InputFormat.SDF) == 1


def test_count_molecules_matches_parse_for_a_multi_record_sdf_with_dollars_mid_line_in_a_field():
    """Same shape as above, but inside a larger, otherwise-normal multi-
    record file -- one spurious mid-line "$$$$" anywhere in a big upload
    must not skew the count for the whole file, not just a single-record
    one.
    """
    data = (
        ETHANOL_MOLBLOCK
        + "> <Note>\nPrice: $$$$ per unit\n\n$$$$\n"
        + BENZENE_MOLBLOCK
        + "$$$$\n"
    ).encode("utf-8")
    assert count_molecules(data, InputFormat.SDF) == len(
        parse(data, InputFormat.SDF, 100)
    )
    assert count_molecules(data, InputFormat.SDF) == 2
