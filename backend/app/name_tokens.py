"""Assign raw name tokens to the decomposition parts that own them.

Spans in this feature are DERIVED, not searched for. `opsin_tokenizer.tokenize`
already returns every token with exact character offsets, so a part's span is
the union of the offsets of the tokens it absorbed. There is no string search
and nothing to prove after the fact.

Why this is a separate module, and why it takes tokens as an argument: the
matcher decides every span the page draws, and a function that needs a live
JVM to test gets tested thinly. Passing the token list in makes the whole
decision table assertable in milliseconds.

Two measured facts shape the algorithm:

* OPSIN's parse tree is an ORDER-PRESERVING SUBSEQUENCE of the token stream,
  not equal to it. It drops elision vowels, hyphens and optional brackets:
  `benzo[a]pyrene` is 4 tokens but 3 tree tokens; `octadecanoic acid` is 6
  and 4; `[1,2,4]triazolo[4,3-a]pyridine` is 10 and 6.
* OPSIN itself MERGES tokens, and token identity does not survive the
  pipeline. Post-buildFragment, `benzo[a]pyrene` is ONE element valued
  `benzo[a]pyren`; identity survivors by hashCode were 1 of 3, and 5 of 13
  for caffeine, whose meth/yl tokens are cloned three times.

So the bridge between offsets (which live pre-ComponentGenerator) and atoms
(which live post-buildFragment) is TEXT: a part's merged value is the
concatenation of the run of raw tokens it absorbed.

A first draft of this module resolved that subsequence gap by letting the
matcher SKIP any non-continuing token, unboundedly, while hunting for where a
part's text picks up again. That is wrong: a part's own text can recur later
in the stream (`purin` also matches inside `...1H-purine...`), so an unbounded
skip lets a part reach forward and claim every token in between as filler --
measured on caffeine itself, where `purin` swallowed the entire
`yl-3,7-dihydro-1H-` modifier region between "meth" and "purin" instead of
just "purine". `app/name_spans.py` already carried the fix for exactly this,
from before this module existed: a part's core text must be a CONTIGUOUS run
(no interior skipping at all), and everything around that core -- locants,
multiplier words, hyphens, elision vowels, the suffix that closes a stem --
is recovered separately, by growing the contiguous anchor outward over a
curated set of decorating categories, bounded by where the NEIGHBOURING run
already starts or ends. `_LEADING`/`_TRAILING` below, and the two-pass anchor-
then-grow shape of `assign_runs`, are that mechanism moved here so both this
module and `name_spans.py` share one definition instead of two that could
drift apart.
"""

from __future__ import annotations

import logging
from typing import NamedTuple, Optional

logger = logging.getLogger(__name__)


class Tok(NamedTuple):
    """One raw token. Mirrors what opsin_tokenizer.tokenize returns."""

    text: str
    category: str
    start: int
    end: int


class Run(NamedTuple):
    """One token run and the part or parts it satisfies.

    `part_indices` holds more than one index only for multiplied clones that
    the name spells once -- caffeine's three `methyl` parts under a single
    `1,3,7-` locant. `fillers` are tokens inside the run that contributed no
    characters to the part's merged value: elision vowels, hyphens, brackets,
    locants and multiplier words. They are recorded rather than discarded
    because the locant spans and the token children are recovered from them.
    """

    part_indices: tuple[int, ...]
    consumed: tuple[int, ...]
    fillers: tuple[int, ...]
    start: int
    end: int


# The single source of truth for which categories decorate a content run and
# which side they decorate it from -- shared with `name_spans.py`, which
# imports both sets from here rather than keeping its own copy. Moved here,
# not copied, so the two callers cannot drift apart.
#
# Tokens that decorate the CONTENT run AFTER them and belong to ITS run:
# "1,3,7-" and "tri" belong to "meth", not to whatever precedes them.
#
# "openBracket" and "stereochemistryBracket" are deliberately NOT here. A
# bracket is structural -- it groups a DIFFERENT run's substituent, not a
# decoration of the run that happens to sit just inside it. With brackets
# in _LEADING, a run's left-growth walked straight through the bracket and
# swallowed the locant token belonging to whatever the bracket encloses:
# in "2-[4-(2-methylpropyl)phenyl]propanoic acid" the methyl's left-growth
# walked all the way back to index 0 and adopted the PARENT propanoic acid's
# "2" as if it were the methyl's own, producing the methyl's span ==
# (0, 14) == "2-[4-(2-methyl" and its locant "2" == (0, 1) instead of the
# methyl's real locant "2" at index 6. Every proof still passed (the text
# is "2" and it sits inside the run's own span) -- this is a confidently
# wrong highlight, not a missing one.
_LEADING = frozenset({
    "locant", "diOrTri", "multiplier", "groupMultiplier",
    "alkaneStemModifier", "cyclo",
    "hyphen", "interSubstituentHyphen",
})

# Tokens that close the content run BEFORE them and belong to ITS run:
# "yl" and the substituent's trailing hyphen belong to "meth".
#
# A plain "hyphen" is deliberately NOT here, only "interSubstituentHyphen".
# In caffeine the hyphen after "purine" is a plain hyphen; absorbing it would
# make the parent span read "purine-" instead of "purine", and would steal the
# character that lets the suffix run claim "-2,6-dione".
#
# "closeBracket" IS deliberately here, and it is the mirror image of the
# _LEADING note above rather than a contradiction of it. Growing LEFT through
# an openBracket is unsafe because the tokens beyond it (a locant) make a real
# claim about atoms that belong to a different run. A closing bracket claims
# no atom at all, so absorbing it can only ever be cosmetic -- ibuprofen's
# spans read "propyl)" and "phenyl]" -- never a wrong letters-to-atoms claim.
# Dropping it would merely move those two characters into the uncovered class
# while perturbing spans that are pinned by measurement.
_TRAILING = frozenset({
    "inlineSuffix", "nonAcidStemSuffix", "suffixesThatCanBeModifiedByAPrefix",
    "e", "ane", "an", "o", "closeBracket",
    "interSubstituentHyphen",
})


def _find_contiguous_anchor(tokens: list, cursor: int, want: str):
    """Find the first position at or after `cursor` where a CONTIGUOUS run of
    tokens concatenates exactly to `want`, with no interior gaps.

    Returns `(start_index, end_index_inclusive)`, or None if no such run
    exists anywhere from `cursor` onward. Trying `want` starting at token `i`
    is abandoned the moment the next token cannot continue it -- there is no
    fallback to skipping ahead within that same attempt, only a fresh
    attempt at `i + 1`. That is what makes this a CONTIGUOUS match rather
    than a subsequence one: a part's own text recurring later in the stream
    (`purin` also occurring inside `...1H-purine...` is not this case, but a
    stem reappearing under a different locant is) must never let this run
    reach across unrelated tokens to find it.
    """
    for start in range(cursor, len(tokens)):
        accumulated = ""
        index = start
        while index < len(tokens) and want.startswith(accumulated + tokens[index].text):
            accumulated += tokens[index].text
            if accumulated == want:
                return start, index
            index += 1
    return None


def _group_locant_matches(tokens: list, start_idx: int, lower_bound: int, wanted: int) -> bool:
    """Does a locant token immediately decorating this anchor list exactly
    `wanted` locants?

    Walks backward from `start_idx` through consecutive `_LEADING`-category
    tokens -- the same walk left-growth performs -- stopping at the first
    token that is not `_LEADING`, or at `lower_bound` (the previous run's raw
    anchor end, so this scan can never reach back over a run already
    assigned). This is what separates caffeine's three cloned methyls under
    `1,3,7-` (wanted=3, found) from two separate `chloro` occurrences that
    merely share a text (never even attempted, since DDT's two `chloro`
    parts are not consecutive in `part_texts`).
    """
    index = start_idx - 1
    while index > lower_bound and tokens[index].category in _LEADING:
        if tokens[index].category == "locant":
            pieces = [p for p in tokens[index].text.replace("-", "").split(",") if p]
            if len(pieces) == wanted:
                return True
        index -= 1
    return False


def assign_runs(tokens: list, part_texts: list) -> Optional[list]:
    """One Run per part group, or None for the WHOLE name.

    None is not an error. It is the honesty rule: a name whose runs cannot be
    accounted for withholds every span rather than shipping some regions live
    and some dead, which would look identical to the reader.

    Two passes. Pass 1 anchors each part (or candidate group of consecutive
    parts sharing one merged value) to a CONTIGUOUS run of raw tokens,
    monotonically left to right. Pass 2 grows each anchor outward over
    `_LEADING`/`_TRAILING` decoration: left growth is bounded by the PREVIOUS
    run's already-grown end (not its anchor -- using the anchor would let a
    run reach back over tokens its neighbour already took, which matters
    because `interSubstituentHyphen` sits in both sets), and right growth is
    bounded by the NEXT run's raw (ungrown) anchor start, so a token both
    neighbours could claim goes to whichever one reaches it via its own
    bound, never both.
    """
    if not tokens or not part_texts:
        # Nothing to anchor on, so nothing can be proven. An empty list would
        # read as success to every caller.
        return None

    # Pass 1: anchor.
    raw_anchors: list = []  # (part_indices, start_idx, end_idx_inclusive)
    cursor = 0
    prev_raw_end = -1
    position = 0
    while position < len(part_texts):
        want = part_texts[position]

        # Consecutive parts sharing a merged value are CANDIDATE clones of one
        # multiplied substituent. Try them as one group first: the name spells
        # a multiplied substituent once, so a group is the only reading that
        # can succeed for caffeine. If the name really does spell the text
        # again later (DDT), the two occurrences are never adjacent in
        # `part_texts` in the first place, so no group is even attempted.
        group_end = position
        while group_end + 1 < len(part_texts) and part_texts[group_end + 1] == want:
            group_end += 1

        anchor = _find_contiguous_anchor(tokens, cursor, want)
        if anchor is None:
            logger.debug(
                "name_tokens: no contiguous run for part %d (%r) from token %d",
                position, want, cursor,
            )
            return None
        start_idx, end_idx = anchor

        group_size = group_end - position + 1
        if group_size > 1 and not _group_locant_matches(tokens, start_idx, prev_raw_end, group_size):
            # The repeats are separate occurrences, not clones under one
            # locant. Take this run for THIS part only and let the next part
            # find its own occurrence.
            group_end = position
            group_size = 1

        raw_anchors.append((tuple(range(position, group_end + 1)), start_idx, end_idx))
        prev_raw_end = end_idx
        cursor = end_idx + 1
        position = group_end + 1

    # Pass 2: grow.
    runs: list[Run] = []
    last_end_index = -1
    for position, (group, start_idx, end_idx) in enumerate(raw_anchors):
        grown_start = start_idx
        while (
            grown_start - 1 > last_end_index
            and tokens[grown_start - 1].category in _LEADING
        ):
            grown_start -= 1
        limit = raw_anchors[position + 1][1] if position + 1 < len(raw_anchors) else len(tokens)
        grown_end = end_idx
        while grown_end + 1 < limit and tokens[grown_end + 1].category in _TRAILING:
            grown_end += 1

        consumed = tuple(range(start_idx, end_idx + 1))
        fillers = tuple(range(grown_start, start_idx)) + tuple(range(end_idx + 1, grown_end + 1))
        runs.append(Run(group, consumed, fillers, tokens[grown_start].start, tokens[grown_end].end))
        last_end_index = grown_end

    # Prove it: non-overlapping and strictly increasing. Construction already
    # guarantees this (each run's grown_start is bounded by the previous run's
    # grown_end), but the check is cheap insurance against a future change to
    # either pass breaking that invariant silently.
    for earlier, later in zip(runs, runs[1:]):
        if earlier.end > later.start:
            logger.debug("name_tokens: runs overlap -- withholding")
            return None
    return runs
