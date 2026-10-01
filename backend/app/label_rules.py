"""The token-kind table (spec §6): which written OPSIN tokens form a part's
label, which are their own child nodes, and which are glue.

Pure Python over WrittenToken lists -- no OPSIN, no JVM -- so it is tested on
stored traces. Kind names are OPSIN's parse-tree element names.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Sequence

from .opsin_trace import Span, WrittenToken

CORE = frozenset({
    "group", "suffix", "unsaturator", "alkaneStemComponent", "heteroatom", "fusion",
    "cyclo", "vonBaeyer", "spiro", "polyCyclicSpiro", "ringAssemblyMultiplier",
    "hydrocarbonFusedRingSystem", "carbohydrateRingSize", "suffixPrefix", "infix", "ine",
    "functionalGroup", "fusedRingBridge", "bridgeFormingO", "alkaneStemModifier",
    "chargeSpecifier",
})
PREFIX = frozenset({
    "stereoChemistry", "indicatedHydrogen", "hydro", "subtractivePrefix", "orthoMetaPara",
    "spiroLocant", "colonOrSemiColonDelimitedLocant", "lambdaConvention",
})
CONTEXTUAL = frozenset({"locant", "multiplier"})
GLUE = frozenset({
    "hyphen", "openbracket", "closebracket", "structuralOpenBracket", "structuralCloseBracket",
})
SUFFIX_KINDS = frozenset({"suffix", "suffixPrefix", "infix"})
LOCANT_KINDS = frozenset({"locant", "colonOrSemiColonDelimitedLocant", "spiroLocant"})

# A copy group's own count ("tri" in trioctadecanoate): value -> count.
MULTIPLIER_COUNTS = {
    "di": 2, "bi": 2, "bis": 2, "tri": 3, "ter": 3, "tris": 3,
    "tetr": 4, "tetra": 4, "tetrakis": 4, "quater": 4,
    "pent": 5, "penta": 5, "pentakis": 5, "hex": 6, "hexa": 6, "hexakis": 6,
    "hept": 7, "hepta": 7, "heptakis": 7, "oct": 8, "octa": 8, "octakis": 8,
}


def is_known(kind: str) -> bool:
    return kind in CORE or kind in PREFIX or kind in CONTEXTUAL or kind in GLUE


def _base(kind: str) -> str:
    if kind in CORE:
        return "core"
    if kind in GLUE:
        return "glue"
    if kind in CONTEXTUAL:
        return "contextual"
    return "prefix"          # PREFIX, and any kind OPSIN adds later


# A locant/multiplier written right before one of these is part of the NAME
# ("1,3,5-tri|azine", "-2,6-di|one", "hepta-1,6-di|ene", "tri|cyclo[...]").
_BUILDS_NAME = frozenset({
    "heteroatom", "fusion", "ringAssemblyMultiplier", "vonBaeyer", "spiro",
    "polyCyclicSpiro", "unsaturator", "alkaneStemComponent",
    "hydrocarbonFusedRingSystem", "suffix", "suffixPrefix", "infix",
})


def resolve_roles(tokens: Sequence[WrittenToken], part_kind: str, copies: int) -> list[str]:
    """A locant/multiplier takes its role from the next non-glue token:

    * before a locant/multiplier -> that token's resolved role (a chain);
    * before a name-building token (_BUILDS_NAME) -> core;
    * a MULTIPLIER before a root's own group -> core ("di|benzo[b,d]furan");
    * anything else -> prefix: before a substituent's group ("4-|methyl"),
      any locant before a group ("alpha-|D-gluco", "1,4-|methano"), before a
      stem modifier or cyclo ("4-|tert-butyl", "1-|cyclopropyl"), before
      hydro or another prefix, or at the end.

    In a copy group, a leading multiplier whose count equals the number of
    copies is that group's own count ("tri|octadecanoate") -> prefix."""
    roles = [_base(t.kind) for t in tokens]
    # A ring-bridge prefix ("4,5-epoxy-17-methylmorphinan") is written before the
    # substituents that follow it, so it can never share the parent's label: it is
    # its own child node.
    roles = ["prefix" if t.kind == "fusedRingBridge" else r for t, r in zip(tokens, roles)]
    nxt: Optional[tuple[str, str]] = None
    for i in range(len(tokens) - 1, -1, -1):
        if roles[i] == "glue":
            continue
        if roles[i] == "contextual":
            if nxt is None:
                roles[i] = "prefix"
            else:
                kind, role = nxt
                if kind in CONTEXTUAL:
                    roles[i] = role
                elif kind in _BUILDS_NAME:
                    roles[i] = "core"
                elif kind == "group" and part_kind == "root" and tokens[i].kind == "multiplier":
                    roles[i] = "core"
                else:
                    roles[i] = "prefix"
        nxt = (tokens[i].kind, roles[i])
    if copies > 1:
        for i, tok in enumerate(tokens):
            if roles[i] == "glue":
                continue
            if tok.kind == "multiplier" and MULTIPLIER_COUNTS.get(tok.value.lower()) == copies:
                roles[i] = "prefix"
            if roles[i] == "core":
                break
    return roles


def covered_positions(tokens: Sequence[WrittenToken]) -> frozenset[int]:
    return frozenset(i for t in tokens for i in range(t.span[0], t.span[1]))


def _extend_letters(text: str, pos: int, covered: frozenset[int]) -> int:
    """Elided/epenthetic letters no token covers ("purin|e") attach left."""
    while pos < len(text) and pos not in covered and text[pos].isalpha():
        pos += 1
    return pos


def balance(text: str, span: Span) -> Span:
    """Pull in a bracket no token covers when the label leaves it open
    ("[1,2,4]triazolo": OPSIN's locant token is "1,2,4", the "[" is bare
    text) or when a closing bracket right after the label is its own."""
    a, b = span
    for o, c in (("(", ")"), ("[", "]"), ("{", "}")):
        while True:
            label = text[a:b]
            if label.count(c) > label.count(o) and a > 0 and text[a - 1] == o:
                a -= 1
            elif label.count(o) > label.count(c) and b < len(text) and text[b] == c:
                b += 1
            else:
                break
    return (a, b)


def label_span(text: str, tokens: Sequence[WrittenToken], roles: Sequence[str],
               covered: frozenset[int], fallback: Span) -> Span:
    core = [t for t, r in zip(tokens, roles) if r == "core"]
    if not core:
        core = [t for t, r in zip(tokens, roles) if r != "glue"]
    if not core:
        return fallback
    return balance(text, (core[0].span[0], _extend_letters(text, core[-1].span[1], covered)))


@dataclass(frozen=True)
class RootSpans:
    parent: Span
    suffix: Optional[Span]          # the whole run, locants included: "2,6-dione"
    suffix_label: Optional[Span]    # the words only: "dione"
    suffix_tokens: frozenset[int]   # WrittenToken.index values in the run


def root_spans(text: str, tokens: Sequence[WrittenToken], roles: Sequence[str],
               covered: frozenset[int], fallback: Span) -> RootSpans:
    suffix_at = [i for i, t in enumerate(tokens) if t.kind in SUFFIX_KINDS and t.value]
    if not suffix_at:
        return RootSpans(label_span(text, tokens, roles, covered, fallback), None, None, frozenset())
    first, last = suffix_at[0], suffix_at[-1]
    run_start = first
    j = first - 1
    while j >= 0:
        if roles[j] == "glue":
            j -= 1
            continue
        if tokens[j].kind in CONTEXTUAL:
            run_start = j
            j -= 1
            continue
        break
    run = tokens[run_start:last + 1]
    start = run[0].span[0]
    if run_start == first:
        # Letters glued to the suffix word belong to it ("propan|oic acid").
        while start > 0 and (start - 1) not in covered and text[start - 1].isalpha():
            start -= 1
    words = [t for t in run if t.kind not in LOCANT_KINDS]
    label_start = start if run_start == first else words[0].span[0]
    parent_core = [t for t, r in zip(tokens[:run_start], roles[:run_start]) if r == "core"]
    if parent_core:
        p_end = min(_extend_letters(text, parent_core[-1].span[1], covered), start)
        parent = balance(text, (parent_core[0].span[0], p_end))
    else:
        parent = fallback
    run_indices = frozenset(t.index for t, r in zip(run, roles[run_start:last + 1]) if r != "glue")
    return RootSpans(parent, balance(text, (start, run[-1].span[1])),
                     balance(text, (label_start, run[-1].span[1])), run_indices)


_LOCANT_ITEM = re.compile(r"[^,:\[\]()\s-]+")
_STEREO_GROUP = re.compile(r"\(([^()]*)\)")
_STEREO_ITEM = re.compile(r"[^,\s]+")
_H_ITEM = re.compile(r"[^,\s-]+")


def locant_items(text: str, span: Span) -> list[tuple[str, Span]]:
    start, end = span
    return [(m.group(0), (start + m.start(), start + m.end()))
            for m in _LOCANT_ITEM.finditer(text[start:end])]


def indicated_h_items(text: str, span: Span) -> list[tuple[str, Span]]:
    start, end = span
    out = []
    for m in _H_ITEM.finditer(text[start:end]):
        item = m.group(0)
        if item.endswith("H"):
            out.append((item[:-1], (start + m.start(), start + m.end())))
    return out


def stereo_items(text: str, span: Span) -> list[tuple[str, Span]]:
    """The individual marks in one written stereo token: every comma-separated
    item inside its parentheses ("(2S,3R)-" -> "2S", "3R"; "rel-(1R,2S)-" ->
    "1R", "2S"; "(E)-" -> "E"; "(+-)-" -> "+-"). A token with no parentheses
    is split on its commas ("3,17beta-" -> "3", "17beta"); "L-" and "trans-"
    are one mark each."""
    start, end = span
    raw = text[start:end]
    items = []
    for group in _STEREO_GROUP.finditer(raw):
        for m in _STEREO_ITEM.finditer(group.group(1)):
            a = start + group.start(1) + m.start()
            items.append((m.group(0), (a, a + len(m.group(0)))))
    if items:
        return items
    inner = raw.rstrip("-")
    # A bare comma list ("3,17beta-" in "...-3,17beta-diol") is split too.
    out, pos = [], start
    for piece in inner.split(","):
        if piece:
            out.append((piece, (pos, pos + len(piece))))
        pos += len(piece) + 1
    return out


# Hantzsch-Widman / replacement prefixes -> the element they put in the ring.
HETERO_ELEMENT = {
    "az": "N", "aza": "N", "ox": "O", "oxa": "O", "thi": "S", "thia": "S",
    "phosph": "P", "phospha": "P", "sil": "Si", "sila": "Si", "bor": "B", "bora": "B",
    "selen": "Se", "selena": "Se", "tellur": "Te", "tellura": "Te", "arsen": "As", "arsa": "As",
    "stib": "Sb", "stiba": "Sb", "germ": "Ge", "germa": "Ge", "stann": "Sn", "stanna": "Sn",
}


def fusion_component_elements(tokens: Sequence[WrittenToken], i: int) -> Optional[list]:
    """For a locant token written at the front of a fusion PREFIX component
    ("[1,3]thiazolo[5,4-b]pyridine": locant, heteroatoms, the ring group, then the
    fusion token), the element each of its numbers puts in the ring, in written
    order ("1,3" + thi,az -> S, N; a counting word repeats its heteroatom:
    "1,2,4" + tri,az -> N, N, N); an unknown prefix gives None for that number.
    None when the locant is not such a component's.

    These numbers belong to the component's OWN numbering. The atoms of the fused
    system carry other numbers, so a fused locant must never be looked up for them."""
    if tokens[i].kind not in LOCANT_KINDS:
        return None
    j = i + 1
    while j < len(tokens) and (tokens[j].kind in CONTEXTUAL or tokens[j].kind == "hyphen"):
        j += 1                                   # a bracket in between ends the component: "2-[(oxazolo..." is the bracket's number
    elements: list = []
    count = 1
    while j < len(tokens) and tokens[j].kind in ("heteroatom", "multiplier"):
        if tokens[j].kind == "multiplier":
            count = MULTIPLIER_COUNTS.get(tokens[j].value.lower(), 1)
        else:
            elements += [HETERO_ELEMENT.get(tokens[j].value.lower())] * count
            count = 1
        j += 1
    if not elements or j >= len(tokens) or tokens[j].kind != "group":
        return None
    after = next((t for t in tokens[j + 1:] if t.kind not in GLUE and t.kind != "hyphen"), None)
    return elements if after is not None and after.kind == "fusion" else None
