"""Which written part -- or which written bracket -- each written token
belongs to (spec §4; the fix for OPSIN's parse-time nesting).

A token OPSIN kept through ComponentProcessor carries its owner already
(``WrittenToken.owner``, recorded by opsin_trace): OPSIN itself put it
there, including hydro prefixes and ring bridges it MOVED into a ring. A
token OPSIN used up (most locants and multipliers, merged alkane stems,
"alpha-", "pyran") is assigned by its written neighbours:

* scan forward: if an opening bracket comes first, a locant / multiplier /
  prefix belongs to THAT BRACKET ("2-[4-(...)phenyl]": the "2-" says where
  the whole bracket attaches; "bis(" counts the bracket). A core token
  never belongs to a bracket ("bi(cyclohexane)", "spiro[...]" name a ring),
  and a used-up core token met on the way decides for the tokens before it
  ("1,1'-bi(cyclohexane)": the locants go where "bi" goes, the ring).
* an ENDING (suffix, unsaturator, ...) follows its group, so it belongs to
  whatever the non-glue token right before it belongs to ("sulfin|yl]";
  the bridge "meth|an|o", all used up, goes where "meth" goes);
* anything else belongs to the part of the first kept token after it
  ("4-|methyl", "alpha-D-|gluco", "benz|imidazole");
* nothing kept on the preferred side -> the other side.

Stereo tokens are assigned too: OPSIN drops some ("L-" in an amino acid)
before a mark can be recorded, and such a token still names its part.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from .label_rules import CORE, GLUE
from .opsin_trace import Span, WrittenToken


OPEN_KINDS = frozenset({"openbracket", "structuralOpenBracket"})
CLOSE_KINDS = frozenset({"closebracket", "structuralCloseBracket"})


def written_brackets(tokens: Sequence[WrittenToken]) -> list[Span]:
    """Matched bracket pairs in the WRITTEN token list: (open start, close end)."""
    out: list[Span] = []
    stack: list[int] = []
    for tok in tokens:
        if tok.kind in OPEN_KINDS:
            stack.append(tok.span[0])
        elif tok.kind in CLOSE_KINDS and stack:
            out.append((stack.pop(), tok.span[1]))
    return out


def innermost_bracket(brackets: Sequence[Span], pos: int) -> Optional[Span]:
    inside = [b for b in brackets if b[0] < pos < b[1]]
    return min(inside, key=lambda b: b[1] - b[0], default=None)


# Used-up tokens that FOLLOW what they belong to.
_ENDINGS = frozenset({
    "suffix", "unsaturator", "infix", "ine", "carbohydrateRingSize", "chargeSpecifier",
})


@dataclass(frozen=True)
class Owner:
    kind: str       # "part" | "bracket"
    span: Span      # the part's key, or the bracket's (open start, close end)


def assign_owners(tokens: Sequence[WrittenToken]) -> dict[int, Optional[Owner]]:
    """WrittenToken.index -> Owner, for every non-glue token.
    A value of None means nothing could own it (counted by the census)."""
    brackets = {b[0]: b for b in written_brackets(tokens)}
    result: dict[int, Optional[Owner]] = {}
    ahead: dict[int, Optional[Owner]] = {}

    def forward(i: int) -> Optional[Owner]:
        """What the tokens after position i give token i. A used-up CORE
        token on the way decides for itself (recursively), so "1,1'-|bi(" is
        owned by the ring "bi" names, not by the bracket after "bi"."""
        if i in ahead:
            return ahead[i]
        tok = tokens[i]
        found: Optional[Owner] = None
        for j in range(i + 1, len(tokens)):
            nxt = tokens[j]
            if nxt.kind in OPEN_KINDS:
                if tok.kind not in CORE and nxt.span[0] in brackets:
                    found = Owner("bracket", brackets[nxt.span[0]])
                    break
                continue
            if nxt.kind in GLUE:
                continue
            if nxt.owner is not None:
                found = Owner("part", nxt.owner)
                break
            if nxt.kind in CORE:
                found = forward(j) or backward(j)
                break
        ahead[i] = found
        return found

    def backward(i: int) -> Optional[Owner]:
        for prev in reversed(tokens[:i]):
            if prev.owner is not None:
                return Owner("part", prev.owner)
        return None

    for i, tok in enumerate(tokens):
        if tok.kind in GLUE:
            continue
        if tok.owner is not None:
            result[tok.index] = Owner("part", tok.owner)
        elif tok.kind in _ENDINGS:
            before = next((p for p in reversed(tokens[:i]) if p.kind not in GLUE), None)
            result[tok.index] = (result.get(before.index) if before is not None else None) \
                or backward(i) or forward(i)
        else:
            result[tok.index] = forward(i) or backward(i)
    return result
