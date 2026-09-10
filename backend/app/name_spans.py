"""Character ranges into the raw IUPAC name for each part of a decomposition.

This is what makes the name itself hoverable. It is deliberately
conservative: it returns None for a whole name rather than emit one span it
cannot prove, because a shifted underline is a confident lie about which
letters mean which atoms -- the exact failure this product forbids.
A name with no spans is not broken; the page falls back to its part list.

Anchoring, and why the obvious approach is wrong. OPSIN's post-processing
parse tree cannot be zipped against the raw token stream: it DROPS locants,
multipliers, hydro, bigCapitalH, cyclo, an and e, and DUPLICATES multiplied
clones. Probed on caffeine:

    RAW : 1,3,7-  tri  meth  yl  -  3,7-  di  hydro  -  1H-  purin  e ...
    TREE:              meth  yl  -  meth  yl  -  meth  yl  -  purin   ...

So each part is anchored on its GROUP token value, matched monotonically
against the raw stream, and its span is then grown outward to the tokens
that decorate it. Four proofs run before anything is returned.
"""

from __future__ import annotations

import logging
from typing import NamedTuple, Optional

from .name_tokens import _LEADING, _MODIFIER, _TRAILING
from .opsin_tokenizer import tokenize

logger = logging.getLogger(__name__)

# _LEADING, _TRAILING (which categories decorate a content token, and from
# which side) and _MODIFIER (which categories mark the hydro / indicated-
# hydrogen run, its own referential part) now live in `name_tokens.py`,
# imported above, since `assign_runs`/`find_modifier_run` there need the
# exact same definitions and a second, drifted copy of the same rationale
# is a defect waiting to happen. See that module for the full comments --
# moved, not duplicated.

# Multiplier tokens, and what each one's text says about HOW MANY instances of
# the following group its own span names. Used only by `claims` below, whose
# job is to let a caller ask "can this one span honestly account for every
# atom my segment owns?".
#
# `tetrOrHigher` is here because OPSIN emits the higher multipliers as TWO
# tokens: "tetra" arrives as ('tetr','tetrOrHigher') + ('a','a'), and "hexa"
# as ('hex','tetrOrHigher') + ('a','a'). Without this category the multiplier
# is invisible, and an unlocanted name like `hexamethylbenzene` -- which has
# no locant list to count instead -- withholds its spans entirely.
_MULTIPLIER_CATEGORIES = frozenset({
    "multiplier", "diOrTri", "groupMultiplier", "tetrOrHigher",
})

# The bare stems below (tetr, pent, hex, ...) are the two-token form's first
# half. Listing "hex" is safe ONLY because the category gate above runs
# first: cyclohexane's "hex" is category alkaneStemTrivial, never
# tetrOrHigher, so it is never looked up here. Do not drop that gate.
_MULTIPLIER_VALUES = {
    "mono": 1, "di": 2, "bis": 2, "tri": 3, "tris": 3,
    "tetra": 4, "tetrakis": 4, "penta": 5, "pentakis": 5,
    "hexa": 6, "hexakis": 6, "hepta": 7, "octa": 8, "nona": 9, "deca": 10,
    "tetr": 4, "pent": 5, "hex": 6, "hept": 7, "oct": 8, "non": 9, "dec": 10,
}

# The modifier's key in `parts`/`locants`, distinct from every legitimate
# `group_tokens` position (which are always >= 0).
MODIFIER_KEY = -1


class SpanSet(NamedTuple):
    # POSITION in the caller's `group_tokens` list (or MODIFIER_KEY) ->
    # (start, end). Keyed by position, not by the group token's text: two
    # different parts of a name can share the same stem text -- ibuprofen's
    # "propyl" substituent and its "propanoic acid" parent both strip to
    # "prop" -- and a text key would collapse both onto one span, handing the
    # parent the substituent's letters. `group_tokens` is expected to carry
    # one entry per span-bearing part, WITH duplicates, in document order;
    # the monotonic anchor below then matches each entry to its own
    # occurrence in the raw name.
    parts: dict
    # part position -> {locant string -> (start, end)}. Nested, NOT flat: a
    # locant string is not unique within a name. Caffeine has three locant
    # tokens ("1,3,7-", "3,7-", "2,6-") and both 3 and 7 appear in two of
    # them. A flat first-wins map would hand the modifier's "3" child the
    # TRIMETHYL's "3" at (2,3) instead of its own at (16,17) -- a span
    # pointing at the wrong letters. Nesting by part, and taking each part's
    # locants only from tokens inside that part's own span, makes
    # child-inside-parent true by construction instead of merely asserted.
    locants: dict
    # part position -> how many instances of its group the span's OWN TEXT
    # claims. This is what lets a caller detect a segment whose atoms come
    # from MORE occurrences of a substituent than its single span covers:
    # `1,1,1-trichloro-` claims three chlorines, so a segment holding five
    # of them is naming two atoms with letters this span does not contain --
    # they are named by the `4-chloro` further along, which no span covers.
    # A span states the count two independent ways: its locant list
    # ("1,3,7-" -> 3) and its multiplier word ("tri" -> 3). Either statement
    # alone is enough to prove the text claims that many, so the larger of
    # the two is taken -- an unlocanted `diethyl` still claims 2, and a
    # multiplier word missing from _MULTIPLIER_VALUES still claims whatever
    # its locants say. Floor of 1: one occurrence always names one instance.
    claims: dict


def _locant_subspans(token) -> dict:
    """Split a locant token into one span per individual locant.

    "1,3,7-" at [0:6] gives 1->(0,1), 3->(2,3), 7->(4,5). Offsets are walked
    rather than searched, so a repeated locant cannot collide.
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
        found.setdefault(piece, (start, start + len(piece)))
        cursor = start + len(piece) + 1
    return found


def compute_spans(
    name: str, group_tokens: list, want_modifier: bool
) -> Optional[SpanSet]:
    """Character ranges for each group token, plus each locant. Returns None
    -- for the WHOLE name -- if anything cannot be proven.
    """
    if not group_tokens:
        # Nothing to anchor on, so nothing can be proven. Returning an empty
        # SpanSet here would read as success to every caller and make the
        # coverage check in step 5 vacuous.
        return None

    tokens = tokenize(name)
    if not tokens:
        return None

    # 1. Anchor each group token to a raw token, monotonically. `group_tokens`
    # carries one entry per span-bearing part, WITH duplicates, in document
    # order -- no dedup here. Two different parts can share the same stem
    # text (ibuprofen's "propyl" substituent and its "propanoic acid" parent
    # both strip to "prop"); the monotonic scan anchors the first occurrence
    # to the first entry and the second occurrence to the second, which is
    # exactly right, and `parts` below is keyed by POSITION so the two never
    # collide.
    anchors = []
    cursor = 0
    for group in group_tokens:
        found = None
        for i in range(cursor, len(tokens)):
            if tokens[i].text == group:
                found = i
                break
        if found is None:
            logger.debug("name_spans: %r has no anchor for %r", name, group)
            return None
        anchors.append((group, found))
        cursor = found + 1

    # 2. Grow each anchor outward over its decorating tokens.
    #
    # The left bound is the previous part's END token, not its anchor. Using
    # the anchor lets a part reach back over tokens its neighbour already
    # took: "interSubstituentHyphen" is in BOTH _LEADING and _TRAILING, so in
    # "2-methyl-1,3,5-trinitrobenzene" the methyl claims the hyphen as its
    # trailing character and nitro then claims the same hyphen as its leading
    # one. Verified: with an anchor-based bound the two spans overlap and the
    # overlap proof in step 5 throws the whole name away.
    parts = {}
    consumed = set()          # token indices already owned by a part
    last_end_index = -1       # END token index of the previous part
    for position, (group, index) in enumerate(anchors):
        start_index = index
        while (
            start_index - 1 > last_end_index
            and tokens[start_index - 1].category in _LEADING
        ):
            start_index -= 1
        limit = anchors[position + 1][1] if position + 1 < len(anchors) else len(tokens)
        end_index = index
        while end_index + 1 < limit and tokens[end_index + 1].category in _TRAILING:
            end_index += 1
        # Keyed by POSITION (this anchor's index in `group_tokens`), not by
        # `group`'s text -- see the SpanSet docstring for why a text key
        # would collide.
        parts[position] = (tokens[start_index].start, tokens[end_index].end)
        consumed.update(range(start_index, end_index + 1))
        last_end_index = end_index

    # 3. The hydro / indicated-hydrogen run, if this molecule has one.
    if want_modifier:
        marks = [i for i, t in enumerate(tokens) if t.category in _MODIFIER]
        if not marks:
            return None
        first, last = marks[0], marks[-1]
        # Same trap, different shape: the modifier is not in the anchor
        # sequence, so it has no `last_end_index` to stop at. Without the
        # `consumed` check it walks back over caffeine's substituent hyphen
        # (token 4) and produces [15,31] against the methyl's [0,16] --
        # verified, and the overlap proof then discards every span for the
        # plan's own headline example.
        while (
            first - 1 >= 0
            and tokens[first - 1].category in _LEADING
            and (first - 1) not in consumed
        ):
            first -= 1
        parts[MODIFIER_KEY] = (tokens[first].start, tokens[last].end)

    # 4. Locants, PER PART -- only from locant tokens inside that part's span.
    #    A flat map would collide: caffeine's 3 and 7 appear in two different
    #    locant tokens meaning two different things.
    locants = {}
    for key, (part_start, part_end) in parts.items():
        found = {}
        for token in tokens:
            if token.category != "locant":
                continue
            if token.start < part_start or token.end > part_end:
                continue
            for locant, span in _locant_subspans(token).items():
                found.setdefault(locant, span)
        locants[key] = found

    # 4b. What each span's own text CLAIMS -- see SpanSet.claims.
    #
    # Counted over the part's DECORATING NEIGHBOURHOOD, not just the span:
    # from the previous part's span end up to this part's own end. A span
    # cannot always reach the tokens that decorate it. `openBracket` is
    # deliberately absent from _LEADING (growing left through a bracket let
    # ibuprofen's methyl adopt the PARENT's locant -- a wrong-atom defect),
    # and a two-token multiplier is not in _LEADING either. So the locant
    # list of `1,1,2,2-tetrachloroethane` sits just outside the chloro span
    # and used to go uncounted, withholding a name whose span was correct.
    #
    # Widening this window can only RAISE claims, which makes the guard
    # withhold LESS -- it can never fabricate a span. Verified: all four
    # wrong-atom Criticals still withhold after this change.
    #
    # One case needs fencing OUT of that widened window, not just left in
    # it: a two-token multiplier's first half (tetr, oct, ...) can decorate
    # a fully-saturating hydro/indicated-hydrogen run that carries NO
    # locant -- "tetr" in "tetrahydrofuran", say. `_collect_modifiers`
    # (opsin_decompose.py) only records a Modifier when its token carries a
    # locant, so an unlocanted run gets no MODIFIER_KEY part here, and
    # nothing bounds this multiplier token's window on the right; it leaks
    # into whichever real part's window reaches it next. Measured live:
    # "1-(tetrahydrofuran-2-yl)-2-(tetrahydrofuran-2-yl)ethane" claimed 4 for
    # its `furanyl` substituent (from the leaked "tetr") instead of 1 --
    # letting a span through for a segment that owns TWO ring occurrences
    # under one first-occurrence span, the exact wrong-atom class this guard
    # exists to catch. A LOCANTED run is unaffected: it gets a real
    # MODIFIER_KEY part, and this same multiplier prefix always sits inside
    # that part's OWN window (nothing else can fall between "oct" and the
    # hydro token it decorates), so it self-counts there, never a different
    # part's -- verified on `octahydro-1H-indene`.
    #
    # This guard is per-NAME, not per-run: a single locanted modifier
    # elsewhere in the name puts MODIFIER_KEY in `parts` and skips the fence
    # for every run, including an unlocanted one that still leaks its
    # multiplier. Not exploitable -- the unlocanted run's own hydro token is
    # itself a mark, so step 3's first-to-last-mark span for MODIFIER_KEY
    # necessarily brackets that leaking multiplier and overlaps the
    # substituent parts between the two runs, and the overlap proof in step
    # 5 throws the whole name away instead of letting the leak through.
    excluded_multipliers = set()
    if MODIFIER_KEY not in parts:
        for i, token in enumerate(tokens):
            if token.category not in _MODIFIER:
                continue
            j = i - 1
            while j >= 0 and tokens[j].category == "a":
                j -= 1
            if j >= 0 and tokens[j].category in _MULTIPLIER_CATEGORIES:
                excluded_multipliers.add(j)

    claims = {}
    previous_end = 0
    for (part_start, part_end), key in sorted((v, k) for k, v in parts.items()):
        pieces, multiplier = 0, 0
        for i, token in enumerate(tokens):
            if token.start < previous_end or token.end > part_end:
                continue
            if token.category == "locant":
                pieces += len(
                    [p for p in token.text.replace("-", "").split(",") if p]
                )
            elif token.category in _MULTIPLIER_CATEGORIES and i not in excluded_multipliers:
                multiplier = max(
                    multiplier, _MULTIPLIER_VALUES.get(token.text.lower(), 0)
                )
        claims[key] = max(pieces, multiplier, 1)
        previous_end = part_end

    # 5. Prove it, or withhold everything.
    for position, (start, end) in parts.items():
        if not (0 <= start < end <= len(name)):
            return None
        if position != MODIFIER_KEY and group_tokens[position] not in name[start:end]:
            logger.debug(
                "name_spans: %r span for %r is %r, which lacks the token",
                name, group_tokens[position], name[start:end],
            )
            return None
    ordered = sorted(parts.values())
    for (_, previous_end), (next_start, _) in zip(ordered, ordered[1:]):
        if previous_end > next_start:
            logger.debug("name_spans: %r produced overlapping spans", name)
            return None
    for key, found in locants.items():
        part_start, part_end = parts[key]
        for locant, (start, end) in found.items():
            if name[start:end] != locant:
                return None
            if not (part_start <= start < end <= part_end):
                return None

    return SpanSet(parts=parts, locants=locants, claims=claims)
