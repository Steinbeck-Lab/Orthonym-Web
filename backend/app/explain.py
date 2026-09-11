"""Name-to-structure explanation: decompose an IUPAC name into a two-level
tree of parts and map each part to the real atoms it names.

The design, the evidence behind it and the failure policy live in the spec:
``docs/superpowers/specs/2026-09-09-explain-token-parts-design.md``. That path
(and ``docs/superpowers/`` generally) is gitignored, so it is not in this repo
-- it lives only on a checkout that has done the planning work under
``.superpowers/sdd/``; do not go hunting for it in git history or on a clone
that lacks it. The short version, because it governs everything below:

* Every atom mapping is traceable to OPSIN's OWN output -- its internal parse
  tree plus its per-atom locants (``opsin_decompose``, ``root_split``). There
  is no SMARTS guessing here. The eight hardcoded SMARTS rules this module
  used to carry were the cause of the defect in spec §1 (caffeine's carbonyls
  sit between ring nitrogens, the ketone SMARTS correctly failed, and the
  whole molecule went blank), not a safety net.
* Failure is PER PART (spec §6). A part whose atoms cannot be resolved is
  emitted with ``kind="unmapped"`` and its siblings are unaffected. Nothing
  here may blank the whole molecule again.
* Owning parts (``substituent``/``parent``/``suffix``) hold disjoint atom sets
  that together cover every heavy atom; referential parts
  (``modifier``/``stereo``) own nothing and carry empty ``atom_indices``
  (spec §4).

Two entry points, differing only in how atom identity is established
(spec §3.4):

* :func:`explain_name` -- name in. OPSIN's own built structure IS the
  molecule, so its atom ids map straight through ``SMILESWriter``'s output
  order to RDKit indices. No substructure match, no symmetry ambiguity.
* :func:`explain_molecule` -- structure in. The molecule is named first, so
  OPSIN's indices belong to a re-parse and must be remapped onto the USER's
  molecule by substructure match, under the all-matches-agree rule ported
  below from ``opsin_substituents``.
"""

import logging
from typing import NamedTuple, Optional

from rdkit import Chem
from rdkit.Chem.Draw import rdMolDraw2D

from openstout import OpenSTOUT

from .glossary import describe_locant, describe_part, describe_token
from .name_tokens import (
    Run,
    Tok,
    _locant_subspans,
    assign_runs,
    collapse_cloned_blocks,
    find_modifier_run,
)
from .opsin_decompose import decompose, heavy_atom_indices
from .opsin_tokenizer import tokenize
from .root_split import split_root

logger = logging.getLogger(__name__)

_EXPLAIN_WIDTH = 340
_EXPLAIN_HEIGHT = 260

# Ported from opsin_substituents (deleted in Task 8), unchanged.
# Generous headroom above what any realistically-drawn small molecule's
# automorphism count needs, so the cap is essentially never hit by a
# genuine case -- see the cap-hit check in explain_molecule for why
# hitting it must mean "inconclusive," never "confirmed."
_MAX_SUBSTRUCT_MATCHES = 4096


def _inline_svg(mol: Chem.Mol) -> tuple[str, list[list[float]]]:
    """Render `mol` as raw (non-data-URI) SVG markup, plus the pixel
    coordinate of every atom in that same drawing.

    The coordinates come from the SAME MolDraw2D instance that produced the
    markup, so the two cannot drift. They exist because RDKit emits a
    standalone atom-N element only for atoms it draws a SYMBOL for --
    caffeine's SVG has standalone classes only at its six heteroatoms, and
    every carbon appears solely inside bond paths like
    `bond-10 atom-7 atom-11`. A highlight built on those elements can never
    light a carbon. Coordinates let the frontend draw its own highlight for
    any atom, which is what the glow needs.
    """
    drawer = rdMolDraw2D.MolDraw2DSVG(_EXPLAIN_WIDTH, _EXPLAIN_HEIGHT)
    drawer.DrawMolecule(mol)
    drawer.FinishDrawing()
    points = []
    for index in range(mol.GetNumAtoms()):
        point = drawer.GetDrawCoords(index)
        points.append([float(point.x), float(point.y)])
    return drawer.GetDrawingText(), points


def _segment(label, kind, explanation, atoms, *, owns=True,
             locant=None, highlight=None, children=None) -> dict:
    return {
        "label": label,
        "kind": kind,
        "owns_atoms": owns,
        "locant": locant,
        "explanation": explanation,
        "atom_indices": sorted(atoms),
        "highlight_atoms": sorted(highlight if highlight is not None else atoms),
        "name_range": None,
        "children": children or [],
    }


def _parent_label(root) -> str:
    """The parent skeleton's own name, without the suffix stuck to it.

    `root.text` is every token in the root concatenated, so it reads
    "purinoneone", "hexol", "ethol", "propic acid" -- visibly broken if shown
    to a user. Stripping the root's own suffix tokens off the end recovers
    OPSIN's <group> token exactly: verified on every golden name --
    purinoneone -> purin, hexol -> hex, acetate -> acet,
    "propic acid" -> prop, benzen -> benzen.

    Strip from the END only, and one occurrence per suffix token, so a stem
    that happens to contain the suffix letters is not mangled.
    """
    label = root.text.strip("-")
    for suffix in reversed(root.suffix_texts):
        if suffix and label.endswith(suffix):
            label = label[: -len(suffix)]
    return label or root.text.strip("-")


def _substituent_stem(part) -> str:
    """The group token behind one substituent PART: "methyl" -> "meth".

    OPSIN's raw group token is what `name_tokens.assign_runs` anchors on, and
    a substituent's own text is that token plus its inline suffix
    ("meth" + "yl"). Per-part twin of `_parent_label` just above -- strip the
    part's own trailing "-", then its own suffix tokens off the end, one
    occurrence each, so a stem that happens to contain the suffix letters is
    not mangled.

    This replaces the old `_strip_suffixes`, which took a SEGMENT's already-
    merged label and re-found a matching part in `result.parts` by text
    equality to get at its suffix tokens -- a lookup that stops making sense
    once parts are no longer pre-merged into one segment per shared text
    before this function is reached (`_build_segments` now groups
    substituents by RUN; two segments can legitimately share a label, so a
    text-equality lookup could find the wrong part's suffix tokens). Callers
    that already hold the part they care about no longer need to ask
    `result.parts` to find it again.
    """
    text = part.text.strip("-")
    for suffix in reversed(part.suffix_texts):
        if suffix and text.endswith(suffix):
            text = text[: -len(suffix)]
    return text


def _locant_sort_key(segment: dict):
    locant = segment.get("locant") or ""
    digits = "".join(c for c in locant if c.isdigit())
    return (int(digits) if digits else 0, locant)


def _bigcapitalh_subspans(token) -> dict:
    """Split a `bigCapitalH`-category token into one span per individual
    locant, less its own trailing "H" marker.

    Unlike a `locant`-category token, a locant here is glued directly to
    the element letter that names it, not set off by a hyphen: "1H-" is
    one locant ("1") stuck to "H"; a fused-ring letter locant keeps its
    own letter ("3aH-" -> "3a", "9bH-" -> "9b" -- confirmed against
    OPSIN's own tokenizer, not assumed). A ring can also carry more than
    one indicated hydrogen in a single token, each spelling its own "H":
    "1H,3H-" -> "1" and "3" (also confirmed live). Offsets are walked
    forward from the token's own start, exactly like `_locant_subspans`,
    so a repeated locant cannot collide with an earlier occurrence.
    """
    found = {}
    cursor = token.start
    for piece in token.text.replace("-", "").split(","):
        if not piece:
            cursor += 1
            continue
        index = token.text.find(piece, cursor - token.start)
        if index < 0:
            continue
        start = token.start + index
        locant = piece[:-1] if piece.endswith("H") else piece
        found.setdefault(locant, (start, start + len(locant)))
        cursor = start + len(piece) + 1
    return found


def _locants_within(tokens: list, start: int, end: int) -> dict:
    """Locant string -> (start, end) for every locant inside `[start, end)`,
    from EITHER of the two token shapes a locant can arrive in.

    A `locant`-category token can carry several locants set off by commas
    ("1,3,7-" is three); a `bigCapitalH`-category token carries its locant
    glued to the element that marks it ("1H-" is one, "1H,3H-" is two).
    Both are walked here, restricted to tokens whose OWN offsets sit
    inside the caller's window, so a repeated locant elsewhere in the name
    cannot collide with this part's own.

    Ported from `name_spans.py`'s per-part locant pass (its step 4; that
    module was deleted in this branch -- read it at `9908574^`), now
    keyed off a run's (or the modifier's) character span directly instead
    of `compute_spans`' anchor-derived one. The `bigCapitalH` branch is new
    here: the ported version only ever walked `locant`-category tokens, so
    an indicated-hydrogen locant living inside a `bigCapitalH` token (like
    caffeine's `1H-`) was invisible to it -- the token simply never matched
    the category filter, not merely mis-split by it.
    """
    found = {}
    for token in tokens:
        if token.start < start or token.end > end:
            continue
        if token.category == "locant":
            for locant, span in _locant_subspans(token).items():
                found.setdefault(locant, span)
        elif token.category == "bigCapitalH":
            for locant, span in _bigcapitalh_subspans(token).items():
                found.setdefault(locant, span)
    return found


def _token_children(segment: dict, tokens: list, run) -> None:
    """Append one child per token in `run` that teaches something on its
    own, to `segment["children"]`.

    Callers append these AFTER the existing locant-child pass has already
    consumed `segment["children"]` by `child["locant"]` (see
    `_apply_name_spans` below). That ordering is load-bearing, not
    incidental: a token child carries `locant=None`, so running the locant
    pass over it would look up `found.get(None)` and just leave its
    `name_range` unset -- harmless by luck (no real locant string is ever
    `None`), but appending here instead keeps that pass walking only the
    locant children it was written for, and each token child gets its span
    from ITS OWN token's offsets, set in this same iteration, never a
    stale value left over from the last token visited.

    Referential, like every other span this feature carries for a token:
    OPSIN gives a fused ring (or a spiro system, or a von Baeyer cage) ONE
    atom set for the whole group, so `benzo` and `pyren` have no separable
    atoms and `[a]` has none at all -- deriving a split would be exactly
    the SMARTS-style guessing `opsin_decompose.py` records as the original
    caffeine defect. `highlight` therefore inherits the OWNING segment's
    own `highlight_atoms`, not its `atom_indices`: for a `modifier` segment
    (`owns_atoms=False`) those two differ -- `atom_indices` is always `[]`
    there, while `highlight_atoms` is the real, resolved parent-atom set
    that segment lights up -- and a token child using `atom_indices` would
    silently highlight nothing.
    """
    for index in sorted(run.consumed + run.fillers):
        token = tokens[index]
        line = describe_token(token.category, token.text)
        if line is None:
            continue
        child = _segment(
            token.text, "token", line, (),
            owns=False, locant=None,
            highlight=tuple(segment["highlight_atoms"]),
        )
        child["name_range"] = [token.start, token.end]
        segment["children"].append(child)


class _SpanPlan(NamedTuple):
    """Everything `_build_segments` and `_apply_name_spans` need to turn a
    decomposition into per-occurrence segments with real spans -- computed
    ONCE, before any segment exists, because segments are now grouped by
    RUN (spec: one written occurrence), and a part cannot be grouped by its
    run before the run is known.

    `run_by_part_id`, `run_by_root_id` and `suffix_run_by_root_id` key by
    `id(...)` -- object identity, not the part's own field values -- because
    two genuinely different parts can carry equal values (DDT's three
    `chloro` parts at locant "1" differ only in their own `opsin_atom_ids`,
    which is exactly the field these maps exist to look up) and identity is
    the only key that can never coincide by accident.
    """

    tokens: list
    run_by_part_id: dict
    run_by_root_id: dict
    suffix_run_by_root_id: dict
    modifier_run: Optional[Run]


def _compute_span_plan(name: str, result) -> Optional[_SpanPlan]:
    """Derive every span this name can PROVE, or None -- the honesty rule:
    a name whose runs cannot be accounted for gets no spans at all, at
    either level this feature has (top-level segment or nested child), and
    `_build_segments` (called with `plan=None`) falls back to grouping
    substituents by TEXT exactly as it always has, so a withheld name's
    part list is unchanged.

    This is the per-occurrence regrouping this module exists for. The old
    version of this function fed `assign_runs` one entry per already-merged
    SEGMENT (`_build_segments` used to group every same-text substituent
    into one segment before spans were ever computed) -- which is why DDT's
    five chlorines could only ever be ONE segment, anchored on its first
    written occurrence alone, silently failing to cover the second. Feeding
    one entry per PART instead (never pre-merged by text) lets a genuinely
    repeated occurrence -- DDT's `chloro` at [0,16) AND again at [24,32) --
    become two separate runs and, downstream in `_build_segments`, two
    separate segments. Caffeine is unaffected: its three methyls carry
    different locants ("1","3","7"), so they were never candidates for
    text-based merging in the first place, and `assign_runs`' own
    consecutive-same-text pass (proven by
    `test_three_multiplied_clones_share_one_run`) still folds them into one
    run here exactly as it always has.

    A `bis`/`tris`/`tetrakis` prefix clones a whole BLOCK of parts, not a
    single part, and spells that block ONCE -- `collapse_cloned_blocks`
    (see its own docstring) folds the block back to one slot per position
    before `assign_runs` ever runs, so the block's single written occurrence
    can still anchor every clone's atoms. Every text `assign_runs` sees below
    is therefore a SLOT's text, not necessarily one part's -- `run.part_indices`
    holds slot positions, expanded back to real part indices via `slots`
    right after `assign_runs` returns.

    Ordering matches what `_build_segments` used to build directly: every
    substituent stem in document order, then each root's own parent label
    and (if it names one) its suffix -- NOT raw `result.parts` order, which
    would interleave substituents and roots and, for names whose root is
    written before its substituents (`sodium 2-hydroxybenzoate`), produce
    keys out of the order `assign_runs`' monotonic scan requires. That
    ordering quirk (and the multi-root suffix-anchor limitation just below)
    are both pre-existing and unchanged by this function -- fixing them is
    the follow-on work the module comment already records, not done here.
    """
    raw = tokenize(name)
    if raw is None:
        logger.info(
            "explain: %r could not be tokenized -- the page will fall back "
            "to the part list", name,
        )
        return None
    tokens = [Tok(t.text, t.category, t.start, t.end) for t in raw]

    first_root = next((p for p in result.parts if p.kind == "root"), None)
    # First root only. A second root's own suffix therefore has no anchor --
    # `sodium acetate`'s `ate` belongs to root 2 -- and the falsy-text branch
    # below withholds the name rather than shipping it partially spanned.
    suffix_key = (
        first_root.suffix_texts[0]
        if (first_root and first_root.suffix_texts) else None
    )

    # One entry per PART, WITH duplicates, in the order described above.
    # `owners` traces an entry back to the real object it spans -- the part
    # itself for a substituent, the root for a parent or suffix -- so
    # `_build_segments` never has to re-derive "which part is this" from a
    # label string the way the old `_strip_suffixes` did.
    keys: list = []
    texts: list = []
    owners: list = []

    for part in result.parts:
        if part.kind == "substituent":
            text = _substituent_stem(part)
            keys.append((text, part.locant))
            texts.append(text)
            owners.append(("substituent", part))
    for root in (p for p in result.parts if p.kind == "root"):
        label = _parent_label(root)
        keys.append((label, None))
        texts.append(label)
        owners.append(("parent", root))
        # Matches `_build_segments`' OWN condition for when it emits a
        # separate suffix SEGMENT, exactly -- `any(root.suffix_texts)` alone
        # is not enough. `split_root` can come back with NO suffix atoms at
        # all even though the root carries suffix TOKENS (measured live on
        # `calcium carbonate`: root "carbonate" has `suffix_texts=("ate",)`,
        # but the ionic split gives it zero separable suffix atoms, so
        # `_build_segments` never emits a suffix segment for it at all).
        # Adding a phantom suffix ENTRY here anyway -- with `suffix_key`
        # read from the FIRST root, "calcium", which has none -- withheld
        # the whole name for a segment that was never going to exist,
        # regressing a name that was CLEAN before this change.
        split = split_root(result, root)
        if split.suffix_atoms and any(root.suffix_texts):
            keys.append((suffix_key, None))
            texts.append(suffix_key)
            owners.append(("suffix", root))

    if not all(texts):
        # A span-bearing entry with no anchorable text cannot be proven, and
        # SKIPPING it is not a neutral act: it leaves that entry's segment
        # `name_range` at None while its siblings keep theirs, which is
        # exactly the partial top-level span set this feature forbids.
        # Measured: `sodium acetate` and `potassium benzoate` shipped that
        # way, because `suffix_key` is read from the FIRST root and their
        # suffix belongs to the second. Withhold instead -- the honest
        # answer is the part list, not half a live name.
        logger.info(
            "explain: %r has a span-bearing entry with no anchorable text "
            "-- the page will fall back to the part list", name,
        )
        return None

    want_modifier = bool(result.modifiers)

    # Try the UNCOLLAPSED entries first, and only fall back to
    # `collapse_cloned_blocks` if that fails. This order matters, and is not
    # just an optimisation: `assign_runs`' own group-size check
    # (`_group_locant_matches`) requires a LOCANT token immediately
    # decorating an anchor, which a hydro-ring substituent's OWN attachment
    # locant never is (`hydro` is not a `_LEADING` category, so the walk
    # stops at it before reaching any locant) -- so two SEPARATELY WRITTEN
    # `tetrahydrofuran-2-yl` occurrences, which OPSIN gives IDENTICAL keys
    # (`("furan", None)` both times -- `part.locant` carries a multiplied
    # clone's own numbering, not the PARENT position a lone substituent
    # attaches at, so two unrelated single occurrences can share it by
    # coincidence), are correctly kept as two separate anchors by
    # `assign_runs` alone. Collapsing them FIRST, unconditionally, would
    # fold both into one slot before `assign_runs` ever saw them separately,
    # anchor that one slot to the FIRST occurrence only, and hand its span
    # atoms that belong to the SECOND, real, physically distinct occurrence
    # too -- measured live before this ordering was fixed. Trying uncollapsed
    # first means `collapse_cloned_blocks` only ever gets a chance to act
    # when the text genuinely does not have enough separate occurrences to
    # go around, which is precisely what a `bis`/`tris`/`tetrakis` clone
    # (and only that) looks like: DDT's `assign_runs` fails on the raw,
    # uncollapsed entries (there is only one written "chlorophenyl", not
    # two), so collapsing that block is the recovery path, not the risk.
    slots = [[index] for index in range(len(keys))]
    runs = assign_runs(tokens, texts)
    if runs is None:
        slots = collapse_cloned_blocks(keys)
        collapsed_texts = [texts[slot[0]] for slot in slots]
        runs = assign_runs(tokens, collapsed_texts)
    if runs is None:
        # Not an error: a name whose spans cannot be PROVEN falls back to the
        # part list by design. Logged at INFO because the fallback is now an
        # expected outcome, and without a line here there is no way to tell
        # which name lost its spans or why.
        logger.info(
            "explain: no proven name spans for %r -- the page will fall back "
            "to the part list", name,
        )
        return None

    modifier_run = None
    if want_modifier:
        modifier_run = find_modifier_run(tokens, runs)
        if modifier_run is None:
            logger.info(
                "explain: no proven name spans for %r -- the page will fall "
                "back to the part list", name,
            )
            return None

    # Expand slot positions back to entry positions, then to the real part
    # or root each entry owns. Every slot appears in exactly one run's
    # `part_indices` (assign_runs partitions its input completely or fails
    # closed for the whole name), so every entry -- and so every part and
    # root -- ends up owned by exactly one run here.
    run_by_entry: dict = {}
    for run in runs:
        for slot_position in run.part_indices:
            for entry_index in slots[slot_position]:
                run_by_entry[entry_index] = run

    # A run may legitimately own more than one SUBSTITUENT entry -- that is
    # the whole point of per-occurrence grouping (caffeine's three cloned
    # methyls; DDT's two written `chloro` occurrences, by way of
    # `collapse_cloned_blocks`). It must never own more than one entry when
    # ANY of them is a `parent` or `suffix` -- those are never multiplied,
    # each names exactly one root's own fixed text, so two of them (or one
    # plus an unrelated substituent) sharing a run can only be a
    # coincidence, not a real clone. Measured live on
    # `N,N-diethylethanamine`: the ROOT's own stem ("ethamine" stripped to
    # "eth") happens to equal the SUBSTITUENT stem it multiplies ("ethyl"
    # stripped to "eth"), and the real "N,N-" locant ahead of the
    # substituent pair (two pieces, genuine evidence for ITS OWN
    # multiplicity) also satisfies `assign_runs`' own group-size check for
    # folding the unrelated parent entry in beside them -- handing the
    # parent segment the substituent's own span ([0,11) "N,N-diethyl")
    # instead of its real one ("ethanamine" at [11,21)). Withhold rather
    # than let a parent or suffix segment borrow a substituent's letters.
    owner_kinds_by_run: dict = {}
    for entry_index, (kind, _obj) in enumerate(owners):
        owner_kinds_by_run.setdefault(id(run_by_entry[entry_index]), []).append(kind)
    for kinds in owner_kinds_by_run.values():
        if len(kinds) > 1 and any(kind != "substituent" for kind in kinds):
            logger.debug(
                "explain: %r withheld -- a run merged entries %r; a parent "
                "or suffix entry is never multiplied, so sharing a run with "
                "anything else can only be a coincidental shared stem",
                name, kinds,
            )
            return None

    run_by_part_id: dict = {}
    run_by_root_id: dict = {}
    suffix_run_by_root_id: dict = {}
    for entry_index, (kind, obj) in enumerate(owners):
        run = run_by_entry[entry_index]
        if kind == "substituent":
            run_by_part_id[id(obj)] = run
        elif kind == "parent":
            run_by_root_id[id(obj)] = run
        else:
            suffix_run_by_root_id[id(obj)] = run

    return _SpanPlan(
        tokens=tokens,
        run_by_part_id=run_by_part_id,
        run_by_root_id=run_by_root_id,
        suffix_run_by_root_id=suffix_run_by_root_id,
        modifier_run=modifier_run,
    )


def _apply_name_spans(segments: list, plan: Optional[_SpanPlan]) -> None:
    """Fill in each top-level segment's (and its children's) `name_range`
    from `plan`, or leave every one of them None if `plan` is None -- the
    honesty rule, never partial at the top level: a response with some
    top-level spans and some not would leave regions of the name dead that
    look identical to live ones.

    `_build_segments` already tagged every top-level segment with the run it
    belongs to (`segment["_run"]`, set while it groups substituent PARTS by
    run instead of by text -- see that function), so this pass no longer
    has to re-derive "which segment does this run belong to" from a label
    string the way the old version did. The temporary `_run` key never
    reaches the API payload either way: this function pops it off every
    segment when `plan` is not None, and `_build_segments` never sets it in
    the first place when `plan` IS None.
    """
    if plan is None:
        return
    for segment in segments:
        run = segment.pop("_run", None)
        if run is None:
            continue
        segment["name_range"] = [run.start, run.end]
        # Locants are nested PER PART, not flat: a locant string is not unique
        # within a name. Caffeine's "3" appears in both "1,3,7-" (the methyls)
        # and "3,7-" (the hydro prefix); a flat lookup would give the modifier
        # the methyls' letters.
        found = _locants_within(plan.tokens, run.start, run.end)
        for child in segment["children"]:
            child_span = found.get(child["locant"])
            if child_span is not None:
                child["name_range"] = list(child_span)
        # Token children go in AFTER the locant pass above, not interleaved
        # with it -- see `_token_children`'s docstring for why the order
        # matters.
        _token_children(segment, plan.tokens, run)


def _build_segments(result, plan: Optional[_SpanPlan]) -> list[dict]:
    """Decompose `result` into the two-level segment tree the page renders.

    `plan` is `_compute_span_plan`'s output (or None -- see that function's
    docstring for when). It changes what a SUBSTITUENT segment is: with a
    plan, parts are grouped by which RUN they belong to (one written
    occurrence -- DDT's two `chloro` occurrences become two segments);
    without one, they fall back to the pre-existing group-by-TEXT behaviour
    (every `chloro` in one segment), because a withheld name still needs a
    part list and there are no runs to group by instead. `parent`, `suffix`
    and `modifier` segments are one per root/modifier-set either way, same
    as always -- only tagged with the run they belong to (`segment["_run"]`,
    consumed and popped by `_apply_name_spans`) when `plan` is not None.
    """
    by_index = {atom.rdkit_index: atom for atom in result.atoms}
    segments: list[dict] = []

    # The DISPLAYED label is the substituent's own full text ("methyl"),
    # never the bare stem `_substituent_stem` computes for anchoring --
    # that stem ("meth") is what `_compute_span_plan` feeds `assign_runs`,
    # but it is not a word a reader should see. Grouping key and label are
    # therefore separate: with a plan, the key is the RUN's identity (so two
    # segments can legitimately share a label, as DDT's two `chloro`
    # segments now do); without one, the key is the full text itself,
    # exactly the pre-existing fallback behaviour.
    substituents = [p for p in result.parts if p.kind == "substituent"]
    grouped: dict = {}
    labels: dict = {}
    group_runs: dict = {}
    for part in substituents:
        text = part.text.strip("-")
        if plan is not None:
            # `assign_runs` (via `_compute_span_plan`) partitions every
            # substituent part into exactly one run when it succeeds at
            # all, so this lookup cannot miss.
            run = plan.run_by_part_id[id(part)]
            key = id(run)
        else:
            run = None
            key = text
        grouped.setdefault(key, []).append(part)
        labels.setdefault(key, text)
        group_runs.setdefault(key, run)

    for key, parts in grouped.items():
        text = labels[key]
        owned = []
        by_locant: dict[str, list] = {}
        for part in parts:
            atoms = heavy_atom_indices(result, part.opsin_atom_ids)
            owned.extend(atoms)
            if part.locant and atoms:
                by_locant.setdefault(part.locant, []).extend(atoms)
        children = []
        for locant, atoms in by_locant.items():
            # No element is passed on purpose. This child's locant is a
            # position in whatever the substituent attaches TO, and the only
            # element available here is the substituent's OWN first atom --
            # a different atom. See describe_locant's docstring for the two
            # reproduced failures and why resolving it against the parent
            # skeleton is not a fix either.
            children.append(
                _segment(locant, "substituent",
                         describe_locant("substituent", locant),
                         atoms, locant=locant)
            )
        children.sort(key=_locant_sort_key)
        segment = _segment(
            text, "substituent",
            describe_part("substituent", text, None, len(owned)),
            owned, children=children,
        )
        if plan is not None:
            segment["_run"] = group_runs[key]
        segments.append(segment)

    # Locant -> atom index, restricted to atoms the PARENT skeleton itself
    # owns. This map is ONLY valid for a locant that is written in the
    # parent's numbering, which is why the modifier loop below consults
    # `Modifier.scope` first and refuses to look a substituent-scoped locant
    # up in here at all.
    # Scanning every atom instead is unsafe: verified live, caffeine's own
    # "1"-methyl substituent carbon carries the OWN-fragment locant "1"
    # (its single carbon, numbered within its own tiny fragment) which
    # collides with the purine ring's N1 also being locant "1" -- the two
    # later clones get primed locants ("1'", "1''") so only this first one
    # collides, but a plain atoms-wide scan would pick whichever atom comes
    # first in SMILES output order, silently mapping "indicatedHydrogen@1"
    # onto a methyl carbon instead of ring N1.
    parent_index_by_locant: dict[str, int] = {}

    for root in (p for p in result.parts if p.kind == "root"):
        split = split_root(result, root)
        for index in split.parent_atoms:
            for locant in by_index[index].locants:
                parent_index_by_locant.setdefault(locant, index)
        parent_label = _parent_label(root)

        # A root can carry suffix ATOMS while naming no suffix at all. The
        # locant split still separates them (phenol's OH oxygen has only the
        # element-symbol locant "O"), but `root.suffix_texts` is empty --
        # "phenol" is one retained <group> token that names the ring AND its
        # OH together, with no <suffix> child to take a name from. Emitting a
        # segment there produced a part labelled the literal word "suffix",
        # which names nothing. There is no honest label to invent, so the
        # atoms stay with the parent that actually names them: degrade, never
        # guess (spec §6). Ownership still partitions the molecule exactly.
        # `any`, not `bool`: OPSIN hands back `('',)` for several retained
        # amino-acid roots -- a suffix token that exists but spells nothing.
        # That tuple is TRUTHY, so `bool` emitted a segment labelled "", whose
        # explanation rendered as '"" covers 2 atoms of this structure.' and
        # whose empty label then fell through the falsy test in
        # `_apply_name_spans`, silently dropping a span-bearing segment and
        # leaving the name PARTIALLY spanned -- the one thing this module
        # forbids. An all-empty tuple is the same "names nothing" case the
        # comment above describes, just wearing a truthy disguise.
        names_its_suffix = any(root.suffix_texts)
        parent_atoms = split.parent_atoms
        if split.suffix_atoms and not names_its_suffix:
            parent_atoms = tuple(sorted(parent_atoms + split.suffix_atoms))

        parent_segment = _segment(
            parent_label, "parent",
            describe_part("parent", parent_label, None, len(parent_atoms)),
            parent_atoms,
        )
        if plan is not None:
            parent_segment["_run"] = plan.run_by_root_id[id(root)]
        segments.append(parent_segment)
        if split.suffix_atoms and names_its_suffix:
            by_locant: dict[str, list] = {}
            for index in split.suffix_atoms:
                locant = split.suffix_locants.get(index)
                if locant is None:
                    continue
                by_locant.setdefault(locant, []).append(index)
            children = []
            for locant, indices in by_locant.items():
                highlight = list(indices) + [
                    i for i in split.parent_atoms
                    if locant in by_index[i].locants
                ]
                # No element is passed on purpose. `indices` are the atoms
                # the SUFFIX owns (caffeine's carbonyl oxygens), but the
                # sentence is about the parent position the group hangs off
                # (C2, C6). Passing the oxygen's element rendered "the group
                # hangs off O2" -- a fabricated atom label.
                children.append(
                    _segment(locant, "suffix",
                             describe_locant("suffix", locant),
                             indices, locant=locant, highlight=highlight)
                )
            children.sort(key=_locant_sort_key)
            # The suffix's NAME comes from the root's own suffix tokens --
            # never a literal. Caffeine gives ("one", "one") -> "dione";
            # an alcohol gives ("ol",) -> "ol". Hardcoding "one" here would
            # tell an alcohol it has a C=O, which the never-guess rule forbids.
            texts = root.suffix_texts
            if len(set(texts)) == 1 and len(texts) > 1:
                multiplier = {2: "di", 3: "tri", 4: "tetra"}.get(len(texts), "")
                suffix_label = f"{multiplier}{texts[0]}"
            else:
                # `texts` is non-empty here -- a root with no suffix tokens
                # never reaches this branch (see names_its_suffix above), so
                # the old `or "suffix"` placeholder is unreachable and gone.
                suffix_label = "".join(dict.fromkeys(texts))
            suffix_segment = _segment(
                suffix_label, "suffix",
                describe_part("suffix", suffix_label, None,
                              len(split.suffix_atoms)),
                split.suffix_atoms, children=children,
            )
            if plan is not None:
                suffix_segment["_run"] = plan.suffix_run_by_root_id[id(root)]
            segments.append(suffix_segment)

    if result.modifiers:
        children, highlight = [], []
        for modifier in result.modifiers:
            # Scope FIRST, lookup second. `parent_index_by_locant` answers
            # every numeric locant the parent happens to carry, whether or
            # not the question was about the parent -- so asking it about a
            # substituent's locant does not fail, it returns a confident
            # wrong atom. Verified: tryptophan's "1H" belongs to INDOLE, a
            # substituent, and resolved to atom 2 of the propanoic parent.
            # The "modifier highlight is a subset of parent atoms" invariant
            # was satisfied by that wrong answer, which is how it survived.
            index = (
                parent_index_by_locant.get(modifier.locant)
                if modifier.scope == "root"
                else None
            )
            if index is None:
                # Not resolvable against the parent -- either it belongs to a
                # substituent, or the parent has no such locant. Either way
                # it stays VISIBLE as `unmapped` (spec §6). Silently skipping
                # it made 1-(2,3-dihydro-1H-inden-5-yl)ethan-1-one lose parts
                # of its name with no trace.
                children.append(
                    _segment(modifier.locant, "unmapped",
                             describe_locant("unmapped", modifier.locant),
                             [], owns=False, locant=modifier.locant,
                             highlight=[])
                )
                continue
            highlight.append(index)
            children.append(
                # The ONLY branch that may name an atom: `index` is a real
                # parent-skeleton atom resolved from this locant in the
                # parent's own numbering. See describe_locant's docstring.
                _segment(modifier.locant, "modifier",
                         describe_locant("modifier", modifier.locant,
                                         by_index[index].element),
                         [], owns=False, locant=modifier.locant,
                         highlight=[index])
            )
        children.sort(key=_locant_sort_key)
        if children:
            modifier_segment = _segment(
                "added hydrogens", "modifier",
                describe_part("modifier", "added hydrogens", None, 0),
                [], owns=False, highlight=highlight, children=children,
            )
            if plan is not None:
                modifier_segment["_run"] = plan.modifier_run
            segments.append(modifier_segment)
    return segments


def explain_name(name: str) -> dict:
    """Decomposes `name` directly. This is the simpler of the two paths:
    OPSIN's own built structure IS the molecule, so atom ids map straight
    through SMILESWriter's output order with no substructure match and no
    symmetry ambiguity.
    """
    result = decompose(name)
    if result is None:
        return {
            "smiles": "", "name": name, "svg": None, "atom_points": [], "total_atoms": 0,
            "segments": [],
            # NOT "OPSIN could not parse this name" -- measured, 23 of 25
            # names that reported that parse fine through the OPSIN 2.9.0
            # CLI, and it fired on names STITCH generated itself
            # (octadecanoic acid). The honest claim is about STITCH.
            "error": "STITCH could not decompose this name.",
        }

    mol = Chem.MolFromSmiles(result.smiles)
    if mol is None:
        return {
            "smiles": result.smiles, "name": name, "svg": None, "atom_points": [],
            "total_atoms": 0, "segments": [],
            "error": "OPSIN parsed this name but the structure could not be read.",
        }

    plan = _compute_span_plan(name, result)
    segments = _build_segments(result, plan)
    _apply_name_spans(segments, plan)
    svg, atom_points = _inline_svg(mol)
    return {
        "smiles": result.smiles,
        "name": name,
        "svg": svg,
        "atom_points": atom_points,
        "total_atoms": mol.GetNumAtoms(),
        "segments": segments,
        "error": None,
    }


def _agreed_atoms(indices, matches) -> Optional[frozenset]:
    """Maps `indices` (RDKit indices into OPSIN's own re-parse) through EVERY
    substructure match, returning the result only if every match agrees on it.

    Ported from ``opsin_substituents._resolve_confirmed_groups``, which Task 8
    deletes. Its reason, from that module's own docstring: "A named
    substituent can be internally SYMMETRIC in the real molecule even though
    the name's own grammar splits it into more than one substituent token
    (ibuprofen's '2-methylpropyl' is OPSIN's 'methyl' substituent + 'propyl'
    substituent, but the actual molecule's isobutyl group has two
    chemically-equivalent terminal methyls -- there is no real structural
    difference between 'the methyl' and 'the propyl chain's own terminal
    carbon'). Confirmed by direct testing: a molecule's substructure match
    against OPSIN's own reconstruction is sometimes NOT unique, and different
    valid matches disagree about which specific carbon is which -- but they
    always agree on the union."

    Returns None when the matches disagree, and also when there are no matches
    at all -- the caller turns either into ``kind="unmapped"`` for that part
    ALONE, never a side of a real symmetry and never a fallback to OPSIN's own
    indices for a molecule they do not describe.

    One deliberate difference from the ported original: it merged adjacent
    disputed candidates and re-checked the union, because its only other
    option was to dump their atoms into one undifferentiated "rest" segment.
    That merge is not carried over. Spec §6 and §8 now say "drop disputed
    groups to unmapped", and per-part `unmapped` already keeps the siblings
    intact -- whereas synthesizing a merged label, kind and children for a
    region the name never spells as one unit would itself be a guess.
    """
    if not matches:
        return None
    sets = []
    for match in matches:
        if any(not 0 <= i < len(match) for i in indices):
            # An index outside the matched fragment cannot be mapped at all.
            # The original wrote this as a FILTER (`if i in m`), which here
            # would silently shrink the segment to its mappable part and ship
            # a partial highlight that looks confident. Unmap the whole
            # segment instead -- "some of these atoms" is not an answer.
            return None
        sets.append(frozenset(match[i] for i in indices))
    if any(s != sets[0] for s in sets):
        return None
    return sets[0]


def _unmapped(segment: dict) -> dict:
    """This part could not be pinned to atoms of the user's molecule. Report
    it honestly -- owning nothing, highlighting nothing -- instead of dropping
    it or letting it take its siblings down with it (spec §6).
    """
    return {
        "label": segment["label"],
        "kind": "unmapped",
        "owns_atoms": False,
        "locant": segment["locant"],
        "explanation": describe_part("unmapped", segment["label"], None, 0),
        "atom_indices": [],
        "highlight_atoms": [],
        "name_range": segment["name_range"],
        "children": [],
    }


def _remap_segment(segment: dict, matches) -> dict:
    """Rewrites one segment's atom indices from OPSIN's re-parse onto the
    user's molecule, recursing into its children. A segment whose atoms (or
    whose highlight) the matches disagree about becomes `unmapped`; its
    children go with it, since a child's atoms are a subset of its parent's
    and cannot be more certain than the parent they sit inside.
    """
    owned = _agreed_atoms(segment["atom_indices"], matches)
    highlight = _agreed_atoms(segment["highlight_atoms"], matches)
    if owned is None or highlight is None:
        return _unmapped(segment)
    return {
        **segment,
        "atom_indices": sorted(owned),
        "highlight_atoms": sorted(highlight),
        "children": [_remap_segment(child, matches) for child in segment["children"]],
    }


def explain_molecule(smiles: str, namer: OpenSTOUT) -> dict:
    """Build an explanation for `smiles`, using `namer` (the SAME primary
    OpenSTOUT instance /api/translate uses, for a consistent name) to name
    it. Returns a dict matching ExplainResponse's shape (see schemas.py).

    The structure-in path of spec §3.4: name the molecule, decompose that
    name, then remap the decomposition onto the USER's molecule -- never
    OPSIN's re-parse, whose atom order is its own. All atom indices returned
    here refer to the SAME RDKit Mol used to render `svg`, parsed exactly
    once, so they are valid for `svg`'s atom-N / bond-N classes with no
    re-indexing.
    """
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return {
            "smiles": smiles,
            "name": None,
            "svg": None,
            "atom_points": [],
            "total_atoms": 0,
            "segments": [],
            "error": "Could not parse this SMILES string",
        }

    tree_result = namer.name_with_tree(smiles)
    name = tree_result.name

    if not name or "unknown" in name.lower():
        return {
            "smiles": smiles,
            "name": None,
            "svg": None,
            "atom_points": [],
            "total_atoms": mol.GetNumAtoms(),
            "segments": [],
            "error": "STITCH could not confidently name this molecule, so "
            "there is nothing to explain.",
        }

    svg, atom_points = _inline_svg(mol)
    total_atoms = mol.GetNumAtoms()

    named = explain_name(name)
    if named["error"] is not None:
        return {
            "smiles": smiles,
            "name": name,
            "svg": svg,
            "atom_points": atom_points,
            "total_atoms": total_atoms,
            "segments": [],
            "error": named["error"],
        }

    # `named`'s indices are into OPSIN's re-parse of the generated name, which
    # is a different Mol with its own atom order. Bridge the two by matching
    # that re-parse against the user's molecule.
    opsin_mol = Chem.MolFromSmiles(named["smiles"])
    matches: tuple = ()
    if opsin_mol is None:
        logger.warning(
            "explain: OPSIN's own SMILES for %r could not be re-read -- "
            "reporting every part as unmapped",
            name,
        )
    elif opsin_mol.GetNumAtoms() != mol.GetNumAtoms():
        # A substructure match does NOT prove the two molecules are the same
        # one. If the generated name re-parses to a PROPER substructure, the
        # match still succeeds and every segment maps happily -- while the
        # user's leftover atoms belong to no segment at all, not even an
        # `unmapped` one, and so vanish from the explanation silently. The
        # old code's "rest of the structure" bucket always absorbed them;
        # nothing does now, so the equality is checked explicitly. A name
        # that does not account for every heavy atom does not describe this
        # molecule, and rule 3 already says what to do about that.
        logger.warning(
            "explain: the name STITCH generated (%r) re-parses to %d heavy "
            "atoms but this molecule has %d -- the name does not describe "
            "the whole structure, so no part of it can be mapped honestly; "
            "reporting every part as unmapped",
            name,
            opsin_mol.GetNumAtoms(),
            mol.GetNumAtoms(),
        )
    else:
        matches = mol.GetSubstructMatches(
            opsin_mol, uniquify=False, maxMatches=_MAX_SUBSTRUCT_MATCHES
        )
        if len(matches) >= _MAX_SUBSTRUCT_MATCHES:
            # Ported from opsin_substituents, reason unchanged: the
            # consistency check in _agreed_atoms only proves anything if we've
            # seen EVERY automorphism -- a molecule symmetric enough to hit
            # this cap could have an unseen automorphism that disagrees with
            # the ones we did see, which is exactly the "arbitrary side of a
            # real symmetry" outcome this check exists to avoid. Treat a
            # capped enumeration as inconclusive, not confirmed.
            logger.warning(
                "explain: substructure match count hit the cap (%d) for %r -- "
                "too symmetric to prove consistency, reporting every part as "
                "unmapped for this molecule",
                _MAX_SUBSTRUCT_MATCHES,
                name,
            )
            matches = ()

    # No matches (none found, or the enumeration was capped and thrown away)
    # makes _agreed_atoms return None for every part, so every segment comes
    # back `unmapped` -- never OPSIN's own indices for a molecule they do not
    # describe.
    segments = [_remap_segment(segment, matches) for segment in named["segments"]]

    return {
        "smiles": smiles,
        "name": name,
        "svg": svg,
        "atom_points": atom_points,
        "total_atoms": total_atoms,
        "segments": segments,
        "error": None,
    }
