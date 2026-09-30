"""Ordering for a batch job's rows.

Sorting lives here rather than in the endpoint because it has to be sorted
ACROSS PAGES, not within one. A page is 50 rows out of up to 10,000, so
sorting what the client already holds would only ever reorder the page it is
looking at -- the request was to bring every abstain onto one screen, and only
a whole-list sort can do that.

The cost is explicit: a sorted request reads and decodes the job's entire row
list, where the default path reads one 50-row slice. That is why `index`
ascending -- the order the rows were submitted in, and the order they are
already stored in -- is handled by the caller as a slice and never reaches
this module.

Every key ends in the row's own index, so the order is TOTAL: two rows never
compare equal, the same request always returns the same rows in the same
order, and paging cannot show a row twice or skip one. For a product whose
first principle is determinism, an unstable page boundary is not a cosmetic
bug.
"""

from typing import Literal, get_args

from app.schemas import VERIFIED_STATUSES, Status

# The confidence ladder, strongest first, derived from the Status literal
# rather than retyped. Status is already declared in ladder order in
# schemas.py, and a second hand-written copy here is how a new tier ends up
# sorting into the wrong half of the table.
_LADDER: tuple[str, ...] = get_args(Status)

SortField = Literal["index", "tier", "name", "roundtrip"]
SortOrder = Literal["asc", "desc"]


def _tier_key(row: dict) -> int:
    """Ladder position. An unrecognised status sorts after every known tier
    rather than before `pin`, which is where `.index()` on a miss would be
    tempting to fake with -1."""
    status = row.get("status")
    return _LADDER.index(status) if status in _LADDER else len(_LADDER)


def _name_key(row: dict) -> tuple[int, str]:
    """Alphabetical, case-folded, with the unnamed rows last.

    The leading flag does the "last" part: sorting `None` against a string
    raises, and substituting "" would file every abstain at the TOP of an
    A-Z sort, which reads as though the engine named them something empty.

    casefold, not lower: an IUPAC name can carry non-ASCII (Greek locants,
    for one), and casefold is the operation defined for caseless matching.
    """
    name = row.get("name")
    return (1, "") if not name else (0, name.casefold())


def _roundtrip_key(row: dict) -> int:
    """Grouped by what the round-trip actually reported, best first.

    Four groups, not three, and the fourth is the one that matters: a pin or
    fallback row with no `roundtrip_smiles` claims a check whose result was
    never recorded. The batch table already calls that out as "unavailable"
    rather than folding it in with the rows that never claimed a check, and
    this sort keeps the two apart for the same reason -- see
    VERIFIED_STATUSES in schemas.py.
    """
    if row.get("roundtrip_smiles"):
        return 0 if row.get("roundtrip_match") else 1
    return 2 if row.get("status") in VERIFIED_STATUSES else 3


_KEYS = {
    "index": lambda row: row.get("index", 0),
    "tier": _tier_key,
    "name": _name_key,
    "roundtrip": _roundtrip_key,
}


def sort_rows(rows: list[dict], field: str, order: str = "asc") -> list[dict]:
    """Return `rows` ordered by `field`, ties broken by index ascending.

    Two passes, and the order of them is the whole trick: Python's sort is
    stable, and `reverse=True` preserves that stability rather than flipping
    equal elements. So sorting by index first and then by the requested field
    leaves ties in index order in BOTH directions. Sorting once on a compound
    key cannot do this -- a descending pass would reverse the tiebreak too,
    and "newest tier first" would silently also mean "last molecule first"
    inside each tier.
    """
    key = _KEYS.get(field)
    if key is None:
        raise ValueError(f"unknown sort field: {field!r}")
    ordered = sorted(rows, key=_KEYS["index"])
    ordered.sort(key=key, reverse=(order == "desc"))
    if field == "name" and order == "desc":
        # The flag that files nameless rows last in A-Z sorts them FIRST once
        # reversed. They have no name at all, so they are not "the last name
        # alphabetically": move them back to the end, still in index order.
        ordered = [r for r in ordered if r.get("name")] + [
            r for r in ordered if not r.get("name")
        ]
    return ordered
