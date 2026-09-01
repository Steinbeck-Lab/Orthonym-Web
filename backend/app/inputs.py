"""Turn an uploaded file or a pasted blob into a list of molecules.

One module serves both the upload endpoint and the paste box, because the
two differ only in transport. Every function here is pure: no Redis, no
Celery, no settings lookup. Limits arrive as an argument so the caller
decides policy and this module only enforces it.

A record that will not parse becomes a ParsedMolecule carrying its own
error. It never aborts the file -- a 5,000-molecule upload with three bad
records should name 4,997 molecules and tell you about the three, not
refuse everything.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from enum import Enum

from rdkit import Chem
from rdkit import RDLogger

# RDKit writes parse failures to stderr by default, which turns a file with
# a few bad records into pages of noise. We report each failure on its own
# row instead, so the global logger is silenced here.
RDLogger.DisableLog("rdApp.*")

# Enough to classify the input without decoding a 50 MB upload.
SNIFF_BYTES = 65536

# A molfile counts line: "<natoms> <nbonds> ... V2000" or V3000.
_COUNTS_LINE = re.compile(r"^\s*\d+\s+\d+.*\bV[23]000\s*$", re.MULTILINE)

_CSV_DELIMITERS = (",", ";", "\t")


class InputFormat(str, Enum):
    SDF = "sdf"
    MOLFILE = "molfile"
    CSV = "csv"
    SMILES_LIST = "smiles_list"


@dataclass
class ParsedMolecule:
    index: int
    raw_input: str
    input_id: str | None
    smiles: str | None
    error: str | None


class TooManyMolecules(Exception):
    """Raised by the per-format parsers once they hit `max_molecules`.

    Carries `partial` -- the rows already built before the limit was hit --
    so a caller previewing a large upload (parse_preview_sample, below) can
    use "the first N I got before this fired" instead of losing them. A
    caller that means to REJECT the whole input outright (app.jobs_api's
    _parse_or_400) just ignores `partial` and 413s, same as before.
    """

    def __init__(self, limit: int, partial: list["ParsedMolecule"] | None = None) -> None:
        super().__init__(f"Input exceeds the {limit}-molecule limit")
        self.limit = limit
        self.partial = partial if partial is not None else []


def _decode(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")


def sniff(data: bytes) -> InputFormat:
    """Classify the input. Order matters: an SDF also contains a counts
    line, so the $$$$ terminator is checked first.
    """
    head = _decode(data[:SNIFF_BYTES])

    if "$$$$" in head:
        return InputFormat.SDF
    if _COUNTS_LINE.search(head):
        return InputFormat.MOLFILE

    lines = head.lstrip().splitlines()
    first = lines[0].strip().lower() if lines else ""
    if first == "smiles":
        # A single-column CSV: no delimiter on the header line.
        return InputFormat.CSV
    if "smiles" in first and any(d in first for d in _CSV_DELIMITERS):
        return InputFormat.CSV

    return InputFormat.SMILES_LIST


def _from_mol(index: int, mol, raw_input: str) -> ParsedMolecule:
    title = mol.GetProp("_Name").strip() if mol.HasProp("_Name") else ""
    return ParsedMolecule(
        index=index,
        raw_input=raw_input,
        input_id=title or None,
        smiles=Chem.MolToSmiles(mol),
        error=None,
    )


def _parse_sdf(data: bytes, max_molecules: int) -> list[ParsedMolecule]:
    rows: list[ParsedMolecule] = []
    # Indexed access, not iteration: on RDKit 2026.3.5, iterating a
    # supplier (Forward or not) over a malformed record makes it believe
    # it has reached the end of the file, silently dropping every record
    # after the bad one. supplier[i] for i in range(len(supplier)) does
    # not have that problem, so records are read by position instead.
    supplier = Chem.SDMolSupplier()
    supplier.SetData(_decode(data), sanitize=True)
    for index in range(len(supplier)):
        if index >= max_molecules:
            raise TooManyMolecules(max_molecules, partial=rows)
        mol = supplier[index]
        if mol is None:
            rows.append(
                ParsedMolecule(
                    index=index,
                    raw_input=f"SDF record {index + 1}",
                    input_id=None,
                    smiles=None,
                    error="RDKit could not read this SDF record",
                )
            )
            continue
        rows.append(_from_mol(index, mol, f"SDF record {index + 1}"))
    return rows


def _parse_molfile(data: bytes, max_molecules: int) -> list[ParsedMolecule]:
    if max_molecules < 1:
        raise TooManyMolecules(max_molecules, partial=[])
    text = _decode(data)
    mol = Chem.MolFromMolBlock(text)
    if mol is None:
        return [
            ParsedMolecule(
                index=0,
                raw_input="molfile",
                input_id=None,
                smiles=None,
                error="RDKit could not read this molfile",
            )
        ]
    return [_from_mol(0, mol, "molfile")]


def _split_smiles_line(line: str) -> tuple[str, str | None]:
    parts = line.split(None, 1)
    if len(parts) == 1:
        return parts[0], None
    return parts[0], parts[1].strip() or None


# Bounds the cost of a SINGLE record, not the batch as a whole (MAX_BATCH_
# SIZE already bounds molecule COUNT; this is the "total-length ceiling"
# from round 3 review, finding 1's third bullet). One absurdly long SMILES
# string is cheap to reject on length alone, before ever calling into
# RDKit -- the measured attack, though, was many MODERATELY sized
# molecules (10,000 x 298 atoms), not one enormous one, and a per-record
# cap does not bound that cumulative cost: parsing 10,000 legitimate
# ~300-atom molecules still costs whatever it costs. That is accepted
# here, not solved -- the parse still runs synchronously in the web
# process before a job can be created at all, and moving it into a worker
# task is a bigger change than this round's scope. What DOES bound it now:
# check_job_allowed runs before this, so a caller is only ever charged
# their hourly/concurrent quota's worth of these parses, not an unlimited
# number per minute the way check_fast_allowed alone would allow.
MAX_MOLECULE_SMILES_LENGTH = 2000


def _canonical_or_error(
    index: int, raw_input: str, smiles: str, input_id: str | None
) -> ParsedMolecule:
    if len(smiles) > MAX_MOLECULE_SMILES_LENGTH:
        return ParsedMolecule(
            index=index,
            raw_input=raw_input,
            input_id=input_id,
            smiles=None,
            error=(
                "SMILES string exceeds "
                f"{MAX_MOLECULE_SMILES_LENGTH} characters"
            ),
        )
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return ParsedMolecule(
            index=index,
            raw_input=raw_input,
            input_id=input_id,
            smiles=None,
            error="Could not parse this SMILES string",
        )
    return ParsedMolecule(
        index=index,
        raw_input=raw_input,
        input_id=input_id,
        smiles=Chem.MolToSmiles(mol),
        error=None,
    )


def _parse_smiles_list(data: bytes, max_molecules: int) -> list[ParsedMolecule]:
    rows: list[ParsedMolecule] = []
    for line in _decode(data).splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if len(rows) >= max_molecules:
            raise TooManyMolecules(max_molecules, partial=rows)
        smiles, input_id = _split_smiles_line(stripped)
        rows.append(_canonical_or_error(len(rows), stripped, smiles, input_id))
    return rows


def _parse_csv(data: bytes, max_molecules: int) -> list[ParsedMolecule]:
    reader = csv.DictReader(io.StringIO(_decode(data)))
    if not reader.fieldnames:
        raise ValueError("CSV has no header row, so no smiles column to read")

    lowered = {name.strip().lower(): name for name in reader.fieldnames}
    if "smiles" not in lowered:
        raise ValueError(
            f"CSV has no smiles column. Columns found: {reader.fieldnames}"
        )
    smiles_col = lowered["smiles"]
    id_col = lowered.get("id") or lowered.get("name")

    rows: list[ParsedMolecule] = []
    for record in reader:
        smiles = (record.get(smiles_col) or "").strip()
        if not smiles:
            continue
        if len(rows) >= max_molecules:
            raise TooManyMolecules(max_molecules, partial=rows)
        input_id = (record.get(id_col) or "").strip() if id_col else ""
        rows.append(
            _canonical_or_error(len(rows), smiles, smiles, input_id or None)
        )
    return rows


_PARSERS = {
    InputFormat.SDF: _parse_sdf,
    InputFormat.MOLFILE: _parse_molfile,
    InputFormat.CSV: _parse_csv,
    InputFormat.SMILES_LIST: _parse_smiles_list,
}


def parse(
    data: bytes, fmt: InputFormat, max_molecules: int
) -> list[ParsedMolecule]:
    """Parse `data` as `fmt`. Raises TooManyMolecules past the limit and
    ValueError for a structurally unusable input (e.g. a CSV with no smiles
    column). Individual bad records become error rows instead.
    """
    return _PARSERS[fmt](data, max_molecules)


def _count_smiles_lines(data: bytes) -> int:
    return sum(1 for line in _decode(data).splitlines() if line.strip())


def _count_csv_rows(data: bytes) -> int:
    reader = csv.DictReader(io.StringIO(_decode(data)))
    if not reader.fieldnames:
        return 0
    lowered = {name.strip().lower(): name for name in reader.fieldnames}
    if "smiles" not in lowered:
        return 0
    smiles_col = lowered["smiles"]
    return sum(1 for record in reader if (record.get(smiles_col) or "").strip())


def _count_sdf_records(data: bytes) -> int:
    """Match Chem.SDMolSupplier's own record count, not just the number of
    "$$$$" terminators (round 4 review: the supplier treats end-of-file as
    an IMPLICIT terminator for a final, unterminated record -- confirmed
    live: a 3-record SDF with its last "$$$$" removed still yields
    len(supplier) == 3, while a bare `.count("$$$$")` would answer 2).

    So: count the terminators actually present, then add one more if
    anything after the LAST one is a real, non-blank record rather than
    trailing whitespace -- and if there are no terminators at all but the
    text is non-blank, that is one single unterminated record, not zero.

    A terminator is a LINE that STARTS WITH "$$$$", not a bare substring
    occurrence anywhere in the text (round 5 review: SDMolSupplier scans
    line-by-line and only treats "$$$$" as a terminator when it opens a
    line -- confirmed live that leading whitespace before it also defeats
    that, e.g. "  $$$$" is not a terminator either -- so a `str.count`
    over the whole blob over-counts an SD data field whose VALUE happens
    to contain the literal string mid-line, e.g. "Price: $$$$ per unit".
    A `$$$$` that IS alone at the start of its own line inside a field's
    value is, confirmed live, still a real terminator to RDKit -- it ends
    that record right there -- so this must keep counting it as one.
    """
    lines = _decode(data).splitlines()
    terminator_indices = [i for i, line in enumerate(lines) if line.startswith("$$$$")]
    count = len(terminator_indices)
    tail_lines = lines[terminator_indices[-1] + 1 :] if terminator_indices else lines
    if any(line.strip() for line in tail_lines):
        count += 1
    return count


_COUNTERS = {
    InputFormat.SDF: _count_sdf_records,
    InputFormat.MOLFILE: lambda data: 1,
    InputFormat.CSV: _count_csv_rows,
    InputFormat.SMILES_LIST: _count_smiles_lines,
}


def count_molecules(data: bytes, fmt: InputFormat) -> int:
    """A STRUCTURAL count -- line count, `$$$$` occurrences, or CSV row
    count -- never RDKit. Used to report `molecule_count` without paying
    for a full parse (see parse_preview_sample, and round 3 review, finding
    1: RDKit-parsing all 10,000 records of a crafted upload just to preview
    5 of them held the GIL for 46 s with no rate limit or job quota
    consumed at all). Not bounded by any max_molecules cap -- it is meant
    to answer "how many molecules are actually in this file," which is a
    question worth answering honestly even for a file too large to submit
    as a job.
    """
    return _COUNTERS[fmt](data)


def parse_preview_sample(
    data: bytes, fmt: InputFormat, sample_size: int
) -> tuple[list[ParsedMolecule], int]:
    """The first `sample_size` records, RDKit-parsed (for a real preview:
    canonical SMILES, per-record errors), plus a cheap structural total
    that never touches RDKit. Never raises TooManyMolecules -- a
    `sample_size`-only parse hitting that limit just means "there were
    more than the sample," which TooManyMolecules.partial already carries.
    """
    try:
        sample = parse(data, fmt, sample_size)
    except TooManyMolecules as exc:
        sample = exc.partial[:sample_size]
    return sample, count_molecules(data, fmt)
