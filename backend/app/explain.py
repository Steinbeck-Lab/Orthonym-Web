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
from typing import Optional

from rdkit import Chem
from rdkit.Chem.Draw import rdMolDraw2D

from openstout import OpenSTOUT

from .glossary import describe_locant, describe_part, describe_token
from .name_tokens import (
    _MODIFIER,
    _MULTIPLIER_CATEGORIES,
    _MULTIPLIER_VALUES,
    Tok,
    _locant_subspans,
    assign_runs,
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


def _strip_suffixes(label: str, result) -> str:
    """The group token behind a substituent label: "methyl" -> "meth".

    OPSIN's raw group token is what `name_tokens.assign_runs` anchors on, and
    a substituent label is that token plus its inline suffix ("meth" + "yl").
    """
    for part in result.parts:
        if part.kind != "substituent":
            continue
        text = part.text.strip("-")
        if text != label:
            continue
        for suffix in reversed(part.suffix_texts):
            if suffix and text.endswith(suffix):
                text = text[: -len(suffix)]
        return text
    return label


def _locant_sort_key(segment: dict):
    locant = segment.get("locant") or ""
    digits = "".join(c for c in locant if c.isdigit())
    return (int(digits) if digits else 0, locant)


def _compute_claims(tokens: list, runs: list, modifier_run) -> dict:
    """Position (in `group_tokens`/`spanned`) -> how many instances of its
    group each run's own text CLAIMS -- e.g. "1,3,7-" + "tri" both say 3.

    Ported from `name_spans.py` (deleted in this branch; read it at `9908574^`)'s per-part claims count (its step 4b), but
    windowed over RUN boundaries (a run's own span plus everything back to
    the previous run's end) instead of `compute_spans`' anchor-derived
    PARTS. A narrower version keyed only to a run's own `fillers` was tried
    first and measurably wrong: `tetrOrHigher` (the "tetr" half of a
    two-token "tetra"/"hexa"/"hepta") is not in `_LEADING`, so it is never
    absorbed into ANY run's fillers, and a `fillers`-only count silently
    dropped to 1 for "tetramethylammonium chloride" -- previously CLEAN,
    wrongly withheld end-to-end. Windowing back to the previous run's end
    recovers it, exactly as it does in `compute_spans`.
    """
    boundaries = sorted(
        list(runs) + ([modifier_run] if modifier_run is not None else []),
        key=lambda r: r.start,
    )

    # An unlocanted hydro/indicated-hydrogen run's own multiplier prefix
    # ("tetr" in tetrahydrofuran) is not absorbed by ANY run either, so with
    # no modifier run to bound it, it would leak into whichever real run's
    # window reaches it next. Ported fence from name_spans.py` (deleted; see `9908574^`):244-270 --
    # skipped whenever this name HAS a modifier run, because then that
    # run's own start already bounds the window (see that module for the
    # measured case: an unlocanted repeated "tetrahydrofuran-2-yl" without
    # this fence inflated a segment's claims from 1 to 4).
    excluded_multipliers = set()
    if modifier_run is None:
        for i, token in enumerate(tokens):
            if token.category not in _MODIFIER:
                continue
            j = i - 1
            while j >= 0 and tokens[j].category == "a":
                j -= 1
            if j >= 0 and tokens[j].category in _MULTIPLIER_CATEGORIES:
                excluded_multipliers.add(j)

    claims: dict = {}
    previous_end = 0
    for run in boundaries:
        pieces, multiplier = 0, 0
        for i, token in enumerate(tokens):
            if token.start < previous_end or token.end > run.end:
                continue
            if token.category == "locant":
                pieces += len(
                    [p for p in token.text.replace("-", "").split(",") if p]
                )
            elif (
                token.category in _MULTIPLIER_CATEGORIES
                and i not in excluded_multipliers
            ):
                multiplier = max(
                    multiplier, _MULTIPLIER_VALUES.get(token.text.lower(), 0)
                )
        for position in run.part_indices:
            claims[position] = max(pieces, multiplier, 1)
        previous_end = run.end
    return claims


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


def _apply_name_spans(name: str, segments: list, result) -> None:
    """Fill in each segment's and child's `name_range`, or leave every one
    of them None. Never partial at the TOP level: a response with some
    top-level spans and some not would leave regions of the name dead that
    look identical to live ones.

    Spans are DERIVED from token offsets (`name_tokens.assign_runs`), not
    searched for by text. The anchor scan this replaced (`compute_spans`,
    formerly in `name_spans.py`, deleted in Task 7 once its only consumer
    -- its own tests -- was the last one left) tested equality against a
    SINGLE raw token, which withheld every fusion-bracket and ring-assembly
    name in the census -- 80 names -- because their labels are several
    tokens wide (`benzo[a]pyrene` merges to one value spanning three raw
    tokens; `assign_runs` anchors on a CONTIGUOUS run instead of one token).
    """
    raw = tokenize(name)
    if raw is None:
        logger.info(
            "explain: %r could not be tokenized -- the page will fall back "
            "to the part list", name,
        )
        return
    tokens = [Tok(t.text, t.category, t.start, t.end) for t in raw]

    # Anchor keys in `_build_segments` order: every substituent stem, then the
    # ring, then the suffix token. `assign_runs` matches monotonically, so the
    # order matters -- but that is NOT a guarantee of document order, and this
    # comment used to claim it was. `_build_segments` emits ALL substituents
    # before ANY root, so a name whose root is written first produces keys out
    # of order: `sodium 2-hydroxybenzoate` yields [hydroxy, sodium, benz, ...]
    # while the name reads `sodium` first. The monotonic scan then cannot
    # anchor them and the whole name withholds -- fail-closed, so nothing
    # incorrect ships, but the cause is invisible from here. Measured: of 34
    # multi-root names in the esters-salts-amides and charged-inorganic axes,
    # 20 are SPANS_NONE, and `trisodium phosphate` has four roots. (That was
    # 18 before the commit which wrote this comment: the same commit moved
    # `sodium acetate` and `potassium benzoate` from partially-spanned to
    # withheld. Re-measure rather than trust it if the withholding rules
    # change again.) Sorting the keys by their roots' document position would
    # recover a real slice of that; it is recorded follow-on work, not done
    # here.
    root = next((p for p in result.parts if p.kind == "root"), None)
    # First root only. A second root's own suffix therefore has no anchor --
    # `sodium acetate`'s `ate` belongs to root 2 -- and the falsy-text branch
    # below withholds the name rather than shipping it partially spanned.
    suffix_key = root.suffix_texts[0] if (root and root.suffix_texts) else None

    def token_for(segment):
        if segment["kind"] == "substituent":
            return _strip_suffixes(segment["label"], result)
        if segment["kind"] == "parent":
            return segment["label"]
        if segment["kind"] == "suffix":
            return suffix_key
        return None

    # One entry per span-bearing segment, WITH duplicates, in document order.
    # `assign_runs` keys its result by POSITION in this list, not by text:
    # two different segments can share the same stem text -- ibuprofen's
    # "propyl" substituent and its "propanoic acid" parent both strip to
    # "prop" -- and a text key would collapse both onto one span, handing the
    # parent the substituent's letters. `spanned` tracks, in the same order,
    # which segment each position belongs to.
    group_tokens: list = []
    spanned: list = []
    for segment in segments:
        if segment["kind"] in ("substituent", "parent", "suffix"):
            text = token_for(segment)
            if not text:
                # A span-bearing segment with no anchorable text cannot be
                # proven, and SKIPPING it is not a neutral act: it leaves that
                # segment's `name_range` at None while its siblings keep
                # theirs, which is exactly the partial top-level span set this
                # function's docstring forbids. Measured: `sodium acetate` and
                # `potassium benzoate` shipped that way, because `suffix_key`
                # is read from the FIRST root and their suffix belongs to the
                # second. The page's own fallback hid it. Withhold instead --
                # the honest answer is the part list, not half a live name.
                logger.info(
                    "explain: %r has a span-bearing %s segment with no "
                    "anchorable text -- the page will fall back to the part "
                    "list", name, segment["kind"],
                )
                return
            group_tokens.append(text)
            spanned.append(segment)

    want_modifier = any(s["kind"] == "modifier" for s in segments)

    runs = assign_runs(tokens, group_tokens)
    if runs is None:
        # Not an error: a name whose spans cannot be PROVEN falls back to the
        # part list by design. Logged at INFO because the fallback is now an
        # expected outcome, and without a line here there is no way to tell
        # which name lost its spans or why.
        logger.info(
            "explain: no proven name spans for %r -- the page will fall back "
            "to the part list", name,
        )
        return

    # `assign_runs`' clone-group pass exists for a caller that hands it ONE
    # entry per RAW part (its own tests do exactly that: caffeine's three raw
    # "methyl" parts, still un-merged). `group_tokens` here is not that -- it
    # is one entry per already-merged SEGMENT (`_build_segments` merges every
    # same-substituent duplicate itself), so two ADJACENT positions sharing
    # text can never legitimately mean "one substituent, multiplied" here;
    # that case has no way to reach this list at all. It can only mean two
    # DIFFERENT segments happen to share a bare stem after suffix-stripping
    # -- measured live on "6,7-dimethoxy-1-methylisoquinoline": the
    # "methoxy" segment's stem and the unrelated "methyl" segment's stem are
    # both "meth", adjacent in document order, and the "6,7-" locant ahead of
    # them satisfies `_group_locant_matches`'s count check by coincidence.
    # `assign_runs` then folds both into ONE run and this function would hand
    # the "methyl" segment the "6,7-dimethoxy-" span -- a wrong letters-to-
    # atoms claim, not just a missing one. Withhold rather than guess.
    for run in runs:
        if len(run.part_indices) > 1:
            logger.debug(
                "explain: %r withheld -- assign_runs merged %d unrelated "
                "segments (positions %r) into one run %r; a legitimate "
                "multiplied substituent is already one segment by the time "
                "it reaches here, so this can only be a coincidental shared "
                "stem",
                name, len(run.part_indices), run.part_indices,
                name[run.start:run.end],
            )
            return

    modifier_run = None
    if want_modifier:
        modifier_run = find_modifier_run(tokens, runs)
        if modifier_run is None:
            logger.info(
                "explain: no proven name spans for %r -- the page will fall "
                "back to the part list", name,
            )
            return

    by_position: dict = {}
    for run in runs:
        for position in run.part_indices:
            by_position[position] = run

    # A grouped substituent segment can own atoms that ITS RUN DOES NOT NAME.
    # `_build_segments` groups substituent parts by TEXT, so every `chloro` in
    # a name lands in one segment, while `assign_runs` anchors that segment
    # on the FIRST occurrence only. Measured live on
    # "1,1,1-trichloro-2,2-bis(4-chlorophenyl)ethane": the chloro segment's
    # run is `1,1,1-trichloro-` (name[0:16]) yet it owns five chlorines, two
    # of which are named by the `4-chloro` at name[24:32] -- text no run
    # covers and which therefore renders inert. Hovering three characters
    # would glow atoms belonging to a different numbering scope. This is
    # precisely the defect class this branch has already fixed three times:
    # a structurally valid region making a false letters-to-atoms claim.
    #
    # The grouping is pre-existing and spec §2 forbids changing the
    # decomposition, so the honest move is to WITHHOLD -- for the whole name,
    # per §4's all-or-nothing rule -- whenever a segment contributes more
    # parts than its run's own text claims. `_compute_claims` reads that
    # claim off each run's own decorating tokens (its locant list and
    # multiplier word), so a substituent multiplied by ONE token keeps
    # working: caffeine's `1,3,7-trimethyl` (3 locants, "tri") and TNT's
    # `1,3,5-trinitro` both claim 3 for 3 parts, and an unlocanted `diethyl`
    # claims 2 for 2 -- all verified.
    #
    # The count MUST be keyed the same way `_build_segments` groups
    # (`part.text.strip("-")`, which is also the segment's label); a different
    # key would silently count the wrong parts.
    #
    # Substituents only, because they are the only grouped-by-text segments:
    # `parent` and `suffix` are emitted one per root, and a multiplied suffix
    # ("dione") is written ONCE in the name, so neither can leave a second
    # occurrence uncovered.
    contributors: dict[str, int] = {}
    for part in result.parts:
        if part.kind == "substituent":
            key = part.text.strip("-")
            contributors[key] = contributors.get(key, 0) + 1
    claims = _compute_claims(tokens, runs, modifier_run)
    for position, segment in enumerate(spanned):
        if segment["kind"] != "substituent":
            continue
        run = by_position.get(position)
        if run is None:
            continue
        owned_by = contributors.get(segment["label"], 1)
        if owned_by > claims.get(position, 1):
            logger.debug(
                "explain: %r withheld -- the %r segment collects %d parts "
                "but its run %r claims only %d, so some of its atoms are "
                "named by text no span covers",
                name, segment["label"], owned_by,
                name[run.start:run.end], claims.get(position, 1),
            )
            return

    for position, segment in enumerate(spanned):
        run = by_position.get(position)
        if run is None:
            continue
        segment["name_range"] = [run.start, run.end]
        # Locants are nested PER PART, not flat: a locant string is not unique
        # within a name. Caffeine's "3" appears in both "1,3,7-" (the methyls)
        # and "3,7-" (the hydro prefix); a flat lookup would give the modifier
        # the methyls' letters.
        found = _locants_within(tokens, run.start, run.end)
        for child in segment["children"]:
            child_span = found.get(child["locant"])
            if child_span is not None:
                child["name_range"] = list(child_span)
        # Token children go in AFTER the locant pass above, not interleaved
        # with it -- see `_token_children`'s docstring for why the order
        # matters.
        _token_children(segment, tokens, run)

    if want_modifier:
        found = _locants_within(tokens, modifier_run.start, modifier_run.end)
        for segment in segments:
            if segment["kind"] != "modifier":
                continue
            segment["name_range"] = [modifier_run.start, modifier_run.end]
            for child in segment["children"]:
                child_span = found.get(child["locant"])
                if child_span is not None:
                    child["name_range"] = list(child_span)
            # Same ordering rule as the loop above: token children go in
            # only after the modifier's own locant children have their
            # spans set.
            _token_children(segment, tokens, modifier_run)


def _build_segments(result) -> list[dict]:
    by_index = {atom.rdkit_index: atom for atom in result.atoms}
    segments: list[dict] = []

    substituents = [p for p in result.parts if p.kind == "substituent"]
    grouped: dict[str, list] = {}
    for part in substituents:
        grouped.setdefault(part.text.strip("-"), []).append(part)

    for text, parts in grouped.items():
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
        segments.append(
            _segment(text, "substituent",
                     describe_part("substituent", text, None, len(owned)),
                     owned, children=children)
        )

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

        segments.append(
            _segment(parent_label, "parent",
                     describe_part("parent", parent_label, None,
                                   len(parent_atoms)),
                     parent_atoms)
        )
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
            segments.append(
                _segment(suffix_label, "suffix",
                         describe_part("suffix", suffix_label, None,
                                       len(split.suffix_atoms)),
                         split.suffix_atoms, children=children)
            )

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
            segments.append(
                _segment("added hydrogens", "modifier",
                         describe_part("modifier", "added hydrogens", None, 0),
                         [], owns=False, highlight=highlight, children=children)
            )
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

    segments = _build_segments(result)
    _apply_name_spans(name, segments, result)
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
