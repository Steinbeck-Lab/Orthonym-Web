"""Explain-coverage census.

Buckets are keyed on the STRUCTURAL FEATURE of the input name (the axis the
corpus assigned), never on what the output looked like, so the result ranks
build order instead of describing symptoms.

Run it directly to print the coverage table:

    cd backend && PYTHONPATH="$(pwd)" REDIS_URL=redis://localhost:6379/0 \
      .venv/bin/python scripts/explain_census.py

Outcomes, which a single name may carry several of:
  ENGINE_ERROR   decompose() failed for this name
  SPANS_NONE     no span-bearing segment got a name_range -- the name text is
                 dead in the UI, because nameTargets() returns []
  SPANS_PARTIAL  some but not all span-bearing segments got a range
  ATOM_GAP       owning segments do not cover every heavy atom
  UNMAPPED       at least one segment came back kind == "unmapped"
"""

import collections
import sys

SPAN_BEARING = ("substituent", "parent", "suffix", "modifier")


def walk(segments):
    for segment in segments:
        yield segment
        yield from walk(segment.get("children") or [])


def classify(payload: dict) -> list[str]:
    """Outcome labels for one explain_name result. ENGINE_ERROR is exclusive:
    a name that never decomposed has no spans to judge, and reporting both
    would double-count it against two different causes.
    """
    if payload.get("error"):
        return ["ENGINE_ERROR"]

    segments = list(walk(payload.get("segments") or []))
    span_bearing = [s for s in segments if s.get("kind") in SPAN_BEARING]
    with_range = [s for s in span_bearing if s.get("name_range") is not None]

    owned = set()
    for segment in segments:
        if segment.get("owns_atoms"):
            owned.update(segment.get("atom_indices") or [])
    atom_gap = (payload.get("total_atoms") or 0) - len(owned)

    outcome = []
    if span_bearing and not with_range:
        outcome.append("SPANS_NONE")
    elif span_bearing and len(with_range) < len(span_bearing):
        outcome.append("SPANS_PARTIAL")
    if any(s.get("kind") == "unmapped" for s in segments):
        outcome.append("UNMAPPED")
    if atom_gap:
        outcome.append("ATOM_GAP")
    return outcome or ["CLEAN"]


def run(corpus) -> list[dict]:
    from app.explain import explain_name

    rows = []
    for index, (axis, name) in enumerate(corpus, 1):
        payload = explain_name(name)
        segments = list(walk(payload.get("segments") or []))
        span_bearing = [s for s in segments if s.get("kind") in SPAN_BEARING]
        rows.append({
            "axis": axis,
            "name": name,
            "outcome": classify(payload),
            "n_span_bearing": len(span_bearing),
            "n_with_range": len([
                s for s in span_bearing if s.get("name_range") is not None
            ]),
            "detail": payload.get("error"),
        })
        if index % 25 == 0:
            print(f"... {index}/{len(corpus)}", file=sys.stderr, flush=True)
    return rows


def table(rows) -> str:
    by_axis = collections.defaultdict(list)
    for row in rows:
        by_axis[row["axis"]].append(row)

    def count(subset, label):
        return sum(1 for r in subset if label in r["outcome"])

    lines = [
        f"{'axis':24s} {'n':>4s} {'clean':>6s} {'spansNONE':>10s} "
        f"{'partial':>8s} {'engErr':>7s} {'unmap':>6s}"
    ]
    for axis in sorted(by_axis):
        subset = by_axis[axis]
        lines.append(
            f"{axis:24s} {len(subset):4d} {count(subset, 'CLEAN'):6d} "
            f"{count(subset, 'SPANS_NONE'):10d} "
            f"{count(subset, 'SPANS_PARTIAL'):8d} "
            f"{count(subset, 'ENGINE_ERROR'):7d} "
            f"{count(subset, 'UNMAPPED'):6d}"
        )
    lines.append(
        f"{'TOTAL':24s} {len(rows):4d} {count(rows, 'CLEAN'):6d} "
        f"{count(rows, 'SPANS_NONE'):10d} {count(rows, 'SPANS_PARTIAL'):8d} "
        f"{count(rows, 'ENGINE_ERROR'):7d} {count(rows, 'UNMAPPED'):6d}"
    )
    return "\n".join(lines)


if __name__ == "__main__":
    from tests.fixtures.explain_corpus import FULL

    print(table(run(FULL)))
