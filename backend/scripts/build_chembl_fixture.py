"""Freeze 10,000 ChEMBL molecules, named once by the Orthonym engine, as
tests/fixtures/explain_chembl_10k.tsv (chembl_id<TAB>name).

    cd backend && PYTHONPATH="$(pwd)" REDIS_URL=redis://localhost:6379/11 \
      .venv/bin/python scripts/build_chembl_fixture.py /home/kohulan/data/chembl/chembl_NN_chemreps.txt.gz

Fixed seed; molecules with 5..80 heavy atoms that RDKit reads; names the
engine abstains on are skipped (nothing to explain), and sampling continues
until 10,000 names are kept.
"""

import gzip
import os
import random
import sys
from pathlib import Path

from rdkit import Chem, RDLogger

from app.orthonym_service import get_primary_namer
from orthonym.errors import is_failure_name

SEED = 20260930
TARGET = 10_000
OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "explain_chembl_10k.tsv"


def main(path: str) -> None:
    RDLogger.DisableLog("rdApp.*")
    with gzip.open(path, "rt") as fh:
        header = fh.readline().rstrip("\n").split("\t")
        id_col, smi_col = header.index("chembl_id"), header.index("canonical_smiles")
        rows = [line.rstrip("\n").split("\t") for line in fh]
    random.Random(SEED).shuffle(rows)
    namer = get_primary_namer()
    kept = []
    for row in rows:
        mol = Chem.MolFromSmiles(row[smi_col])
        if mol is None or not 5 <= mol.GetNumHeavyAtoms() <= 80:
            continue
        name = namer.name_with_tree(row[smi_col]).name
        if is_failure_name(name) or "\t" in name:
            continue
        kept.append(f"{row[id_col]}\t{name}")
        if len(kept) % 500 == 0:
            print(f"{len(kept)} kept", flush=True)
        if len(kept) == TARGET:
            break
    OUT.write_text("\n".join(kept) + "\n")
    print(f"wrote {len(kept)} rows to {OUT}", flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
    os._exit(0)   # the JVM would otherwise keep the process alive
