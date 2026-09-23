"""Real name tokenization via OPSIN's own parser -- not a guess.

NOW LOAD-BEARING. `explain.py` imports `tokenize` from this module and
builds every `name_range` in the Explain response on its character offsets,
which is the work this module was kept for -- "Spans come instead from
`ParseRules.getParses()`, which `opsin_tokenizer.py` already turns into exact
character offsets with a full-reconstruction check" (spec §4). Until the
2026-08-16 name-driven-UI branch it was genuinely unused: the SMARTS-based
suffix detection it was first built to feed had been deleted along with
`explain.py`'s `_SUFFIX_RULES`, and `opsin_decompose.py` reaches the same
name parts a different way (OPSIN's internal post-buildFragment parse tree,
which carries real atom fragments this public tokenizer cannot). That
character-offset machinery, and the two verified constraints documented
below, are what made it worth keeping; re-deriving them would have cost the
same testing again.

`find_suffix_span` below has no caller. It is retained for the same reason
the module itself was, and its behaviour is the documented evidence for the
two suffix categories the constraints section names.

One line below is now historical rather than current: the paragraph about
`explain.py`'s "rest of the structure" segment describes the retired design.
There is no `rest` segment any more -- a part that cannot be resolved is
reported per-part as `kind="unmapped"`.

OPSIN's job is to parse an IUPAC name INTO a structure, and to do that it
must first tokenize the name into its real grammatical pieces (parent stem,
unsaturation markers, suffix, locants, brackets, substituent boundaries).
That tokenizer is exposed as public API
(``uk.ac.cam.ch.wwmm.opsin.NameToStructure.getOpsinParser().getParses(name)``,
returning ``ParseTokens`` with parallel ``getTokens()``/``getAnnotations()``
lists) -- this module calls that API directly via jpype and decodes each
token's one-letter annotation into a real semantic category, using the
symbol -> category table OPSIN's own grammar file (``regexes.xml``, vendored
under backend/vendor/opsin-resources/) defines. This replaces guessing at a
name's suffix from how the rendered string happens to end with asking
OPSIN's actual grammar what each piece of the name IS.

Two real constraints, confirmed by direct testing against the live vendored
jar (not assumed):

1. ``getParses()`` does not always span a multi-word name in one call -- a
   two-word retained acid name like "acetic acid" tokenizes as one parse
   spanning both words, but a two-word ester name like "methyl acetate"
   only consumes the first word ("methyl") and silently leaves "acetate"
   unconsumed. Silently accepting a partial parse would misplace every
   downstream character offset, so `tokenize` first tries the whole string
   and REQUIRES the tokens to reconstruct it exactly; only on that
   verification failing does it fall back to tokenizing each space-
   separated word independently and re-joining with the real space
   characters preserved.
2. A bare substituent group name (e.g. "phenyl", "methylpropyl") does NOT
   parse standalone via this same top-level API -- confirmed by testing --
   because OPSIN's word-level grammar expects a full parent+suffix name,
   not a bare substituent fragment. So this module can tell you WHERE a
   substituent chunk sits in the name and what OPSIN's tokenizer calls it,
   but not resolve it to its own independent structure fragment; that
   would require OPSIN's non-public, substituent-specific grammar entry
   points. explain.py's "rest of the structure" segment (parent chain +
   substituents, highlighted as one region via atom set-subtraction, never
   sub-divided) is the honest consequence of this real limitation.

Two annotation categories reliably mark a principal-characteristic-group
suffix token, verified across every functional-group class this app
recognizes (alcohol, ketone, amine, aldehyde, amide, nitrile, carboxylic
acid, ester) plus multiplied forms (diol, dione, dial via a preceding
di/tri multiplier token): ``nonAcidStemSuffix`` and
``suffixesThatCanBeModifiedByAPrefix``. A multiplier token
(``diOrTri``) immediately preceding one of these is included as part of
the same suffix span, since "di" + "ol" reads as one suffix, "diol".
"""

from __future__ import annotations

import re
import threading
from typing import NamedTuple, Optional

from orthonym.validation.opsin_roundtrip import PROJECT_ROOT

_SUFFIX_CATEGORIES = frozenset({"nonAcidStemSuffix", "suffixesThatCanBeModifiedByAPrefix"})
_MULTIPLIER_CATEGORY = "diOrTri"

_REGEXES_PATH = (
    PROJECT_ROOT
    / "opsin/opsin-core/src/main/resources/uk/ac/cam/ch/wwmm/opsin/resources/regexes.xml"
)
_REGEX_LINE = re.compile(r'<regex name="%([^%]+)%" value="(.)"/>')

_lock = threading.Lock()
_symbol_to_category: Optional[dict] = None
_opsin_parser = None  # cached uk.ac.cam.ch.wwmm.opsin.ParseRules instance
_load_attempted = False


class Token(NamedTuple):
    text: str
    category: str
    start: int
    end: int  # exclusive, so name[start:end] == text


def _load_symbol_table() -> dict:
    global _symbol_to_category
    if _symbol_to_category is not None:
        return _symbol_to_category
    table = {}
    if _REGEXES_PATH.exists():
        with open(_REGEXES_PATH, encoding="utf-8") as f:
            for line in f:
                match = _REGEX_LINE.match(line.strip())
                if match:
                    table[match.group(2)] = match.group(1)
    _symbol_to_category = table
    return table


def _get_parser():
    """Returns OPSIN's ParseRules instance, or None if Java/the JVM/the
    vendored jar isn't available. Reuses the SAME shared JVM the engine's own
    SELF-01 gate already starts (via opsin_available()) rather than booting
    a second one -- jpype allows exactly one JVM per process.
    """
    global _opsin_parser, _load_attempted
    if _opsin_parser is not None:
        return _opsin_parser
    if _load_attempted:
        return None
    with _lock:
        if _opsin_parser is not None or _load_attempted:
            return _opsin_parser
        _load_attempted = True
        try:
            from orthonym.jvm_bridge import opsin_available

            if not opsin_available():
                return None
            import jpype
            import jpype.imports  # noqa: F401  -- enables `from uk.ac...` style access

            name_to_structure = jpype.JClass("uk.ac.cam.ch.wwmm.opsin.NameToStructure")
            _opsin_parser = name_to_structure.getOpsinParser()
        except Exception:
            _opsin_parser = None
    return _opsin_parser


def _tokenize_raw(text: str) -> Optional[list]:
    """One getParses() call. Returns (tokens, annotations) for the first
    candidate parse, or None if OPSIN found no parse at all for `text`.
    """
    parser = _get_parser()
    if parser is None:
        return None
    try:
        results = parser.getParses(text)
        parse_list = results.getParseTokensList()
        if not parse_list:
            return None
        first = parse_list[0]
        tokens = [str(t) for t in first.getTokens()]
        annotations = [str(a) for a in first.getAnnotations()]
        return list(zip(tokens, annotations))
    except Exception:
        return None


def tokenize(name: str) -> Optional[list]:
    """Tokenizes `name` via OPSIN's real parser, returning a list of Token
    with exact character offsets into `name`. Returns None when OPSIN/the
    JVM is unavailable, or when no parse could be constructed that exactly
    reconstructs `name` (never returns a token list for a partial/wrong
    reconstruction).
    """
    symbol_table = _load_symbol_table()

    def to_tokens(pairs, base_offset):
        """Builds Token objects whose `.text` is sliced from the ORIGINAL
        `name` at the offsets OPSIN's own token lengths walk out -- never
        OPSIN's returned text verbatim. OPSIN's ParseRules matches some
        tokens case-insensitively and hands the token back lowercased
        (`D-` comes back as `d-`); trusting that text directly would make
        a span's highlighted characters differ from what the page
        renders. Also returns OPSIN's own raw joined text (unsliced) so
        the caller can verify the parse against `name`/`word`
        case-insensitively -- comparing the sliced tokens back against
        the very string they were sliced from would always trivially
        match and could no longer catch a partial parse.
        """
        tokens = []
        raw_pieces = []
        pos = base_offset
        for text, symbol in pairs:
            if not text:
                continue
            category = symbol_table.get(symbol, symbol)
            end = pos + len(text)
            tokens.append(Token(text=name[pos:end], category=category, start=pos, end=end))
            raw_pieces.append(text)
            pos = end
        return tokens, pos, "".join(raw_pieces)

    whole = _tokenize_raw(name)
    if whole is not None:
        tokens, _, raw_joined = to_tokens(whole, 0)
        # Full reconstruction confirmed character-for-character -- a PARTIAL
        # parse ("methyl acetate" consumes only "methyl") has to fall through to
        # the multi-word path below.
        #
        # This was three spellings of that one comparison -- an `end_pos ==
        # len(name)` guard, a sliced-prefix comparison, and then the join again
        # -- which read as three separate conditions and joined the token text
        # twice per call. They collapse because `end_pos` is the sum of the
        # token lengths: if the joined text equals `name` then `end_pos ==
        # len(name)` follows, and the empty-token case reduces to `"" == name`
        # on both sides.
        #
        # OPSIN's ParseRules matches some tokens case-insensitively
        # (ParseRules.java:97-107, 146-158) and returns the token LOWERCASED --
        # `D-` comes back as `d-`. Comparing exactly rejected OPSIN's own
        # correct answer and killed every D-/L- sugar and amino acid. Compare
        # case-folded instead, against `raw_joined` -- OPSIN's own text, before
        # slicing -- so a genuinely partial parse (still shorter than `name`
        # under casefold too) is still rejected exactly as before.
        if raw_joined.casefold() == name.casefold():
            return tokens

    # Multi-word fallback (e.g. ester names like "methyl acetate"): tokenize
    # each space-separated word independently, re-joining with the real
    # space characters so offsets still index into the original `name`.
    words = name.split(" ")
    if len(words) < 2:
        return None
    all_tokens = []
    pos = 0
    for i, word in enumerate(words):
        if word:
            pairs = _tokenize_raw(word)
            if pairs is None:
                return None
            word_tokens, new_pos, raw_joined = to_tokens(pairs, pos)
            # Same case-fold relaxation as the whole-name guard above, and for
            # the same reason: OPSIN can lowercase a `D-`/`L-` token inside a
            # single word of a multi-word name too (e.g. the second word of
            # "methyl beta-D-galactopyranoside"). The length check stays
            # case-sensitive-strict -- it is what actually catches a word this
            # loop only partially consumed.
            if new_pos - pos != len(word) or raw_joined.casefold() != word.casefold():
                return None
            all_tokens.extend(word_tokens)
            pos = new_pos
        if i < len(words) - 1:
            pos += 1  # the space character itself, not represented as a Token

    if pos == len(name):
        return all_tokens
    return None


def find_suffix_span(name: str) -> Optional[tuple]:
    """Finds the principal-characteristic-group suffix's exact text and
    character span in `name`, using OPSIN's own tokenizer -- not a regex
    guess at how the string ends. A multiplier token (di/tri) immediately
    before a suffix token is included in the same span ("di" + "ol" ->
    "diol"), since that's how the multiplied suffix actually reads.

    Returns (suffix_text, start, end), or None if OPSIN tokenization isn't
    available or no token in this name carries a suffix category.
    """
    tokens = tokenize(name)
    if not tokens:
        return None

    suffix_indices = [i for i, t in enumerate(tokens) if t.category in _SUFFIX_CATEGORIES]
    if not suffix_indices:
        return None

    # The LAST suffix-categorized token is the one that actually closes the
    # name (P-14.5: suffix comes last) -- relevant for names with an
    # internal suffix-like token that isn't the final principal group.
    idx = suffix_indices[-1]
    start = tokens[idx].start
    if idx > 0 and tokens[idx - 1].category == _MULTIPLIER_CATEGORY:
        start = tokens[idx - 1].start
    end = tokens[idx].end
    return name[start:end], start, end
