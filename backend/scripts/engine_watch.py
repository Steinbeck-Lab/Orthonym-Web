"""Name a fixed panel with the installed engine and report what changed.

The engine is installed from its main branch, so an engine push can change a
name or a tier with no commit here. The build's SELF-01 check notices only
when a Home example breaks, at deploy time. This runs nightly
(.github/workflows/engine-watch.yml) against the panel in
tests/fixtures/engine_watch.tsv and says, per molecule, what moved.

    python scripts/engine_watch.py                 # compare, print the report
    python scripts/engine_watch.py --report r.md --out new.tsv
    python scripts/engine_watch.py --write         # accept: rewrite the panel

Exit codes: 0 nothing changed, 1 something changed, 2 the run itself failed.
Run it on Linux (CI or the backend image) before committing a panel: the
names are the engine's, but RDKit's canonical SMILES can differ by platform.
"""

import argparse
import csv
import os
import sys
from pathlib import Path

PANEL = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "engine_watch.tsv"
FIELDS = ["id", "smiles", "status", "tier", "name"]
# An issue body holds 65,536 characters; past this many rows the table stops
# and says how many it left out. Every row is still in the artifact.
MAX_ROWS = 150


def read_panel(path: Path) -> tuple[str, list[dict]]:
    lines = path.read_text().splitlines()
    engine = lines[0].removeprefix("# engine ").strip() if lines[0].startswith("#") else "unknown"
    rows = list(csv.DictReader([line for line in lines if not line.startswith("#")], delimiter="\t"))
    return engine, rows


def write_panel(path: Path, engine: str, rows: list[dict]) -> None:
    with path.open("w", newline="") as f:
        f.write(f"# engine {engine}\n")
        writer = csv.DictWriter(f, fieldnames=FIELDS, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def name_panel(rows: list[dict]) -> list[dict]:
    from app.orthonym_service import translate_one

    out = []
    for row in rows:
        got = translate_one(row["smiles"], best_effort=True, depict=False)
        out.append({"id": row["id"], "smiles": row["smiles"], "status": got.status, "tier": got.tier or "", "name": got.name or ""})
    return out


def report(old_engine: str, new_engine: str, old: list[dict], new: list[dict], broken: list[str]) -> tuple[str, int]:
    before = {r["id"]: r for r in old}
    changed = [(before[r["id"]], r) for r in new if (before[r["id"]]["status"], before[r["id"]]["tier"], before[r["id"]]["name"]) != (r["status"], r["tier"], r["name"])]
    lines = [
        f"## Engine watch: {len(changed)} of {len(new)} molecules changed",
        "",
        f"Panel named with engine `{old_engine}`; this run used `{new_engine}`.",
        "",
    ]
    if broken:
        lines += ["**Home examples that no longer match their badge** (the next backend build will fail):", ""]
        lines += [f"- {b}" for b in broken] + [""]
    if changed:
        lines += ["| id | SMILES | was | now |", "|---|---|---|---|"]
        for was, now in changed[:MAX_ROWS]:
            lines.append(f"| {now['id']} | `{now['smiles']}` | {was['status']} · {was['name'] or '—'} | {now['status']} · {now['name'] or '—'} |")
        if len(changed) > MAX_ROWS:
            lines += ["", f"…and {len(changed) - MAX_ROWS} more (all in the run's artifact)."]
        run_id = os.environ.get("GITHUB_RUN_ID", "<run-id>")
        lines += [
            "",
            "If the new names are right, accept them by committing this run's panel:",
            "",
            "```bash",
            f"gh run download {run_id} -n engine-watch-panel -D backend/tests/fixtures/",
            "```",
        ]
    return "\n".join(lines) + "\n", 1 if changed or broken else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true", help="rewrite the panel with this engine's results")
    parser.add_argument("--report", type=Path, help="also write the markdown report here")
    parser.add_argument("--out", type=Path, help="write this run's panel here")
    args = parser.parse_args()

    from app.engine_info import ENGINE_COMMIT, ENGINE_VERSION
    from app.main import EXAMPLES
    from app.orthonym_service import translate_one

    engine = f"{ENGINE_VERSION} {ENGINE_COMMIT or ''}".strip()
    old_engine, old = read_panel(PANEL)
    new = name_panel(old)
    if args.out:
        write_panel(args.out, engine, new)
    if args.write:
        write_panel(PANEL, engine, new)
        print(f"wrote {len(new)} rows to {PANEL}")
        return 0

    broken = [
        f"{ex['label']}: advertised `{ex['expected_status']}`, engine returns `{got}`"
        for ex in EXAMPLES
        if (got := translate_one(ex["smiles"], best_effort=True, depict=False).status) != ex["expected_status"]
    ]
    text, code = report(old_engine, engine, old, new, broken)
    print(text)
    if args.report:
        args.report.write_text(text)
    return code


if __name__ == "__main__":
    try:
        code = main()
    except Exception as exc:  # the run failed; that is not "something changed"
        print(f"engine watch failed: {exc!r}", file=sys.stderr)
        code = 2
    sys.stdout.flush()
    # A started JVM will not let the interpreter exit (see CLAUDE.md, Tests).
    os._exit(code)
