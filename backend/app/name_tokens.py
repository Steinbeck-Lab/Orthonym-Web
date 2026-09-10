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


# Two shapes of trailing connective token are safe to sweep into the run that
# just finished, rather than left for the next part to claim as a leading
# filler (the default, via the non-matching-prefix skip in `_match_one`
# below): an elision vowel and a hyphen. Both are safe because neither
# carries an identity of its own that could be misattributed -- unlike a
# locant (whose digits belong to whichever part they introduce) or a bracket
# or multiplier word (which conventionally open what comes AFTER them, not
# close what came before). OPSIN's tokenizer names an elision-vowel category
# after the letter itself, so the category string equals one of these three
# single characters -- confirmed against `regexes.xml` (`%a%`, `%e%`,
# `%o%`), and matching the measured drops in `benzo[a]pyrene` (trailing `e`)
# and `octadecanoic acid` (`a`, `o`).
_ELISION_VOWEL_CATEGORIES = frozenset({"a", "e", "o"})


def _is_trailing_filler_category(category: str) -> bool:
    """Would this token's own category mark it as unsemantic connective
    material that CLOSES the word just matched, rather than opening the
    next one?

    Only elision vowels and hyphens qualify -- see the module-level comment
    above for why locants, brackets and multiplier words are deliberately
    excluded even though the docstring on `Run.fillers` lists them as filler
    kinds in general: those still end up recorded as fillers, just as
    LEADING fillers of the next run, which is where their identity actually
    belongs.
    """
    if category in _ELISION_VOWEL_CATEGORIES:
        return True
    return "hyphen" in category.lower()


def _match_one(tokens: list, cursor: int, want: str):
    """Consume tokens from `cursor` until their concatenation equals `want`,
    then greedily sweep any immediately following unsemantic tokens into the
    same run.

    Returns (consumed, fillers, next_cursor) or None. A token whose text does
    not continue `want` is a filler and is skipped -- that is what makes this
    a subsequence match rather than a contiguous one, and it is required
    because the parse tree drops tokens the stream keeps.

    Once `want` is exactly built, a hyphen or elision vowel sitting right
    after it (e.g. caffeine's trailing `-` after `methyl`, or `benzo[a]pyrene`'s
    trailing `e`) is swept in too: it closes this word rather than opening the
    next one, and if this is the LAST part there is no next run to claim it as
    a leading filler at all -- it would otherwise dangle, unclaimed by
    anything, which is what left the trailing `e`/`-` out of the run entirely
    in an earlier draft of this function.
    """
    accumulated = ""
    consumed: list[int] = []
    fillers: list[int] = []
    index = cursor
    while index < len(tokens) and accumulated != want:
        text = tokens[index].text
        if want.startswith(accumulated + text):
            accumulated += text
            consumed.append(index)
        else:
            fillers.append(index)
        index += 1
    if accumulated != want:
        return None
    while index < len(tokens) and _is_trailing_filler_category(tokens[index].category):
        fillers.append(index)
        index += 1
    return consumed, fillers, index


def assign_runs(tokens: list, part_texts: list) -> Optional[list]:
    """One Run per part group, or None for the WHOLE name.

    None is not an error. It is the honesty rule: a name whose runs cannot be
    accounted for withholds every span rather than shipping some regions live
    and some dead, which would look identical to the reader.
    """
    if not tokens or not part_texts:
        # Nothing to anchor on, so nothing can be proven. An empty list would
        # read as success to every caller.
        return None

    runs: list[Run] = []
    cursor = 0
    position = 0
    while position < len(part_texts):
        want = part_texts[position]

        # Consecutive parts sharing a merged value are CANDIDATE clones of one
        # multiplied substituent. Try them as one group first: the name spells
        # a multiplied substituent once, so a group is the only reading that
        # can succeed for caffeine. If the name really does spell the text
        # again later (DDT), the group attempt still consumes exactly one
        # occurrence and the next part matches the next occurrence -- so
        # falling through to a per-part run happens naturally.
        group_end = position
        while group_end + 1 < len(part_texts) and part_texts[group_end + 1] == want:
            group_end += 1

        matched = _match_one(tokens, cursor, want)
        if matched is None:
            logger.debug(
                "name_tokens: no run for part %d (%r) from token %d",
                position, want, cursor,
            )
            return None
        consumed, fillers, next_cursor = matched

        group = tuple(range(position, group_end + 1))
        if len(group) > 1 and not _locant_count_matches(tokens, consumed, fillers, len(group)):
            # The repeats are separate occurrences, not clones under one
            # locant. Take this run for THIS part only and let the next part
            # find its own occurrence.
            group = (position,)

        start = tokens[min(consumed + fillers)].start
        end = tokens[max(consumed + fillers)].end
        runs.append(Run(group, tuple(consumed), tuple(fillers), start, end))
        cursor = next_cursor
        position = group[-1] + 1

    # Prove it: non-overlapping and strictly increasing.
    for earlier, later in zip(runs, runs[1:]):
        if earlier.end > later.start:
            logger.debug("name_tokens: runs overlap -- withholding")
            return None
    return runs


def _locant_count_matches(tokens: list, consumed, fillers, wanted: int) -> bool:
    """Does a locant token inside this run list exactly `wanted` locants?

    This is what separates caffeine's three cloned methyls under `1,3,7-`
    from two separate `chloro` occurrences that merely share a text.
    """
    for index in consumed + fillers:
        token = tokens[index]
        if token.category != "locant":
            continue
        pieces = [p for p in token.text.replace("-", "").split(",") if p]
        if len(pieces) == wanted:
            return True
    return False
