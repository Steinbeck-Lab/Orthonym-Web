"""One OPSIN run gives Explain everything it needs: the atoms of every name
part, the text position of every written token, which part OPSIN itself put
each token in, and OPSIN's own kind for each token.

Design and evidence: docs/superpowers/specs/2026-09-30-explain-opsin-trace-
design.md (gitignored; local checkouts only).

How it works, in the order OPSIN runs:

1. ``Parser.parse``. Every ``TokenEl`` gets a ``stitchSpan`` attribute, its
   [start, end) offset in the text OPSIN read (R1, case-insensitive: OPSIN
   stores "L-" as "l"). Every grouping element gets a ``stitchPart`` range,
   min..max of its non-stereo tokens (R3). The ``stitchPart`` range is only
   an IDENTITY KEY for a part: OPSIN's ``Element.copy()`` carries attributes,
   so the clones ``buildFragment`` makes share their original's key. It is
   NOT where the part's text is -- at parse time a bracket's leading locant
   and its "[" sit inside the bracket's FIRST substituent (OPSIN's parser has
   no bracket element), so parse-time ranges over-reach.
2. ``ComponentGenerator`` + ``ComponentProcessor``. OPSIN now USES UP many
   written tokens (locants become ``locant`` attributes on new ``bracket``
   elements, multipliers and alkane stems merge), and MOVES others: hydro
   prefixes, subtractive prefixes and ring bridges ("3,7-dihydro",
   "1,4-methano") are detached from their own substituent and put into the
   ring they modify. So after this step every token that is still in the tree
   records its OWNER: the key of the part OPSIN placed it in
   (``WrittenToken.owner``). Tokens OPSIN used up keep ``owner=None``;
   ``app/token_owner.py`` assigns them by their written neighbours.
   Stereo tokens are NOT read from this tree: OPSIN splits and moves them
   but may leave a word-leading set parked in the wrong part (measured:
   "(2S)-" stays in "amino" in "(2S)-2-aminopropanoic acid"), and
   ``buildFragment`` consumes them anyway. app/explain_tree.py reads stereo
   from the WRITTEN tokens instead, by IUPAC's own scoping rule.
3. ``StructureBuilder.buildFragment``. Clones are made; every part's atoms
   are read from its fragments.

Every class and most methods used are package-private in OPSIN, unlocked by
reflection against the exactly pinned jar (orthonym/jars.py fetches
opsin-cli 2.9.0 by SHA-256). If any lookup fails the module disables itself
and every call returns TraceFailure("unavailable"). Each run is also checked
against OPSIN's PUBLIC parseToSmiles; a traced molecule that differs is
rejected ("mismatch"), never shown.

Failures, all of them refusals (never a partial trace):

- "unavailable": the reflection handles could not be resolved.
- "unreadable": OPSIN itself cannot read the name.
- "mismatch": the traced molecule is not the one OPSIN's public parse gives.
- "unplaced": OPSIN read the name but the parts cannot be tied to the text.
  OPSIN reads a CAS index name ("benzoic acid, 4-amino-, ethyl ester") in
  uninverted form, so its tokens no longer run in written order: R1 can place
  only some of them, and a part with no token of its own would otherwise share
  a neighbour's key and light the wrong atoms. A part takes its key only from
  its own tag or from an enclosing substituent/root, never from a word or
  molecule.

Celery's SoftTimeLimitExceeded subclasses Exception; it is re-raised, never
turned into a failure.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import asdict, dataclass, replace
from functools import cmp_to_key
from typing import Optional, Union

from celery.exceptions import SoftTimeLimitExceeded
from rdkit import Chem

logger = logging.getLogger(__name__)

PINNED_OPSIN_VERSION = "2.9.0"
TOKEN_TAG = "stitchSpan"
PART_TAG = "stitchPart"
_NO_SPAN = "none"
_PART_KINDS = ("substituent", "root")
STEREO_KIND = "stereoChemistry"

Span = tuple[int, int]


@dataclass(frozen=True)
class TraceAtom:
    index: int                    # RDKit heavy-atom index into Trace.smiles
    opsin_id: int
    element: str
    locants: tuple[str, ...]      # OPSIN's own locants, e.g. ("1", "N")


@dataclass(frozen=True)
class WrittenToken:
    index: int                    # position in Trace.tokens
    kind: str                     # OPSIN parse-tree element name ("group", "locant", ...)
    value: str                    # OPSIN's value; may differ from the text in case only
    span: Span                    # [start, end) into Trace.text
    # Key (TracePart.span) of the part OPSIN placed this token in after
    # ComponentProcessor; None when OPSIN used the token up (see token_owner).
    owner: Optional[Span] = None


@dataclass(frozen=True)
class TracePart:
    index: int
    kind: str                     # "substituent" | "root"
    span: Optional[Span]          # identity key (parse-time range); copies share it
    locant: Optional[str]         # OPSIN's resolved LOCANT_ATR on this copy
    atoms: tuple[int, ...]        # heavy-atom indices


@dataclass(frozen=True)
class Trace:
    text: str                     # the string OPSIN read (after its PreProcessor)
    smiles: str
    atoms: tuple[TraceAtom, ...]
    tokens: tuple[WrittenToken, ...]
    parts: tuple[TracePart, ...]


@dataclass(frozen=True)
class TraceFailure:
    # "unavailable" | "unreadable" | "mismatch" | "unplaced"
    # ("unplaced": OPSIN read the name in a reordered form, e.g. a CAS index
    # name, so its parts cannot be matched to the written text).
    reason: str


class _Unplaceable(Exception):
    """OPSIN read the name, but its parts cannot be tied to the written text."""


# --------------------------------------------------------------------------
# Reflection handles
# --------------------------------------------------------------------------

def _raw_class(c):
    return c if hasattr(c, "isInstance") else c.class_


def _unlock_field(cls, name):
    f = cls.class_.getDeclaredField(name)
    f.setAccessible(True)
    return f


def _unlock_method(cls, name, *params):
    m = cls.class_.getDeclaredMethod(name, *[_raw_class(p) for p in params])
    m.setAccessible(True)
    return m


def _unlock_ctor(cls, *params):
    c = cls.class_.getDeclaredConstructor(*[_raw_class(p) for p in params])
    c.setAccessible(True)
    return c


class _Handles:
    """Every reflection handle, resolved once. Construction raises if OPSIN's
    internal shape changed; the caller then disables the module."""

    def __init__(self):
        import jpype
        import jpype.imports  # noqa: F401

        J = jpype.JClass
        pkg = "uk.ac.cam.ch.wwmm.opsin."
        self.NameToStructure = J(pkg + "NameToStructure")
        self.NameToStructureConfig = J(pkg + "NameToStructureConfig")
        self.BuildState = J(pkg + "BuildState")
        self.Parser = J(pkg + "Parser")
        self.ComponentGenerator = J(pkg + "ComponentGenerator")
        self.ComponentProcessor = J(pkg + "ComponentProcessor")
        self.SuffixApplier = J(pkg + "SuffixApplier")
        self.SuffixRules = J(pkg + "SuffixRules")
        self.StructureBuilder = J(pkg + "StructureBuilder")
        self.Element = J(pkg + "Element")
        self.TokenEl = J(pkg + "TokenEl")
        self.Attribute = J(pkg + "Attribute")
        self.Fragment = J(pkg + "Fragment")
        self.FragmentManager = J(pkg + "FragmentManager")
        self.SMILESWriter = J(pkg + "SMILESWriter")
        self.SmilesOptions = J(pkg + "SmilesOptions")
        self.Atom = J(pkg + "Atom")
        self.PreProcessor = J(pkg + "PreProcessor")
        self.SortParses = J(pkg + "SortParses")
        JString = J("java.lang.String")
        JInt = J("java.lang.Integer").TYPE

        self.preprocess = _unlock_method(self.PreProcessor, "preProcess", JString)
        self.sort_parses = _unlock_ctor(self.SortParses).newInstance()

        self.nts = self.NameToStructure.getInstance()
        version = self.version = str(self.NameToStructure.getVersion())
        if version != PINNED_OPSIN_VERSION:
            logger.warning(
                "opsin_trace: running against OPSIN %s, pinned/tested version is %s",
                version, PINNED_OPSIN_VERSION,
            )

        self.parser = _unlock_field(self.NameToStructure, "parser").get(self.nts)
        self.suffix_rules = _unlock_field(self.NameToStructure, "suffixRules").get(self.nts)
        self.config = self.NameToStructureConfig.getDefaultConfigInstance()
        self.state_ctor = _unlock_ctor(self.BuildState, self.NameToStructureConfig)
        self.parse_method = _unlock_method(self.Parser, "parse", self.NameToStructureConfig, JString)
        self.cg_ctor = _unlock_ctor(self.ComponentGenerator, self.BuildState)
        self.cg_process = _unlock_method(self.ComponentGenerator, "processParse", self.Element)
        self.sa_ctor = _unlock_ctor(self.SuffixApplier, self.BuildState, self.SuffixRules)
        self.cp_ctor = _unlock_ctor(self.ComponentProcessor, self.BuildState, self.SuffixApplier)
        self.cp_process = _unlock_method(self.ComponentProcessor, "processParse", self.Element)
        self.sb_ctor = _unlock_ctor(self.StructureBuilder, self.BuildState)
        self.build_fragment = _unlock_method(self.StructureBuilder, "buildFragment", self.Element)
        self.convert_spare_valencies = _unlock_method(
            self.FragmentManager, "convertSpareValenciesToDoubleBonds"
        )
        self.sw_ctor = _unlock_ctor(self.SMILESWriter, self.Fragment, JInt)
        self.write_smiles = _unlock_method(self.SMILESWriter, "writeSmiles")
        self.output_order_field = _unlock_field(self.SMILESWriter, "smilesOutputOrder")
        self.default_smiles_opts = _unlock_field(self.SmilesOptions, "DEFAULT").get(None)

        self.get_name = _unlock_method(self.Element, "getName")
        self.get_children = _unlock_method(self.Element, "getChildElements")
        self.get_parent = _unlock_method(self.Element, "getParent")
        self.get_frag = _unlock_method(self.TokenEl, "getFrag")
        self.get_value = _unlock_method(self.TokenEl, "getValue")
        self.get_attribute_value = _unlock_method(self.Element, "getAttributeValue", JString)
        self.get_attribute = _unlock_method(self.Element, "getAttribute", JString)
        self.add_attribute = _unlock_method(self.Element, "addAttribute", JString, JString)
        self.set_attribute_value = _unlock_method(self.Attribute, "setValue", JString)
        self.get_atom_list = _unlock_method(self.Fragment, "getAtomList")
        self.get_id = _unlock_method(self.Atom, "getID")
        self.get_locants = _unlock_method(self.Atom, "getLocants")
        self.get_atom_element = _unlock_method(self.Atom, "getElement")
        self.frag_manager_field = _unlock_field(self.BuildState, "fragManager")
        self.get_warnings = _unlock_method(self.BuildState, "getWarnings")


_lock = threading.Lock()
_handles: "Optional[_Handles] | bool" = None


def _get_handles() -> Optional[_Handles]:
    global _handles
    if _handles is not None:
        return _handles or None
    with _lock:
        if _handles is not None:
            return _handles or None
        try:
            from orthonym.jvm_bridge import opsin_available

            if not opsin_available():
                _handles = False
                return None
            _handles = _Handles()
            logger.info("opsin_trace: internal reflection API verified OK")
        except Exception:
            logger.exception(
                "opsin_trace: OPSIN's internal API shape is unavailable or has "
                "changed -- Explain is disabled; naming is unaffected"
            )
            _handles = False
    return _handles or None


def running_opsin_version() -> Optional[str]:
    """The version of the OPSIN jar actually loaded, or None when tracing is
    unavailable (no JVM, or OPSIN's internal shape changed)."""
    h = _get_handles()
    return None if h is None else h.version


def self_check() -> bool:
    """Resolve every handle once at worker boot, so a wrong jar is a loud
    boot-time log line rather than a silent Explain outage."""
    return _get_handles() is not None


# --------------------------------------------------------------------------
# Tree helpers
# --------------------------------------------------------------------------

def _is_token(h, el) -> bool:
    return bool(h.TokenEl.class_.isInstance(el))


def _name(h, el) -> str:
    return str(h.get_name.invoke(el))


def _value(h, el) -> str:
    return str(h.get_value.invoke(el))


def _children(h, el) -> list:
    ch = h.get_children.invoke(el)
    return [ch.get(i) for i in range(ch.size())]


def _tokens(h, el, out=None) -> list:
    out = [] if out is None else out
    if _is_token(h, el):
        out.append(el)
    else:
        for child in _children(h, el):
            _tokens(h, child, out)
    return out


def _read_span(h, el, tag) -> Optional[Span]:
    raw = h.get_attribute_value.invoke(el, tag)
    if raw is None or str(raw) == _NO_SPAN:
        return None
    start, end = str(raw).split(":")
    return (int(start), int(end))


def _write_span(h, el, tag, span: Optional[Span]) -> None:
    text = _NO_SPAN if span is None else f"{span[0]}:{span[1]}"
    attr = h.get_attribute.invoke(el, tag)
    if attr is None:
        h.add_attribute.invoke(el, tag, text)
    else:
        h.set_attribute_value.invoke(attr, text)


def _owner_key(h, el) -> Optional[Span]:
    """Key of the nearest enclosing part that carries a part tag."""
    parent = h.get_parent.invoke(el)
    while parent is not None:
        if _name(h, parent) in _PART_KINDS:
            key = _read_span(h, parent, PART_TAG)
            if key is not None:
                return key
        parent = h.get_parent.invoke(parent)
    return None


# --------------------------------------------------------------------------
# 1. Tags written right after parse (R1, R3)
# --------------------------------------------------------------------------

def _stamp_tokens(h, parse_el, text: str) -> list[WrittenToken]:
    """R1. Walk the fresh parse in document order and find each token's value
    in the text from a moving cursor, case-insensitively."""
    lowered = text.lower()
    cursor = 0
    written: list[WrittenToken] = []
    valued = 0
    first_unfound: Optional[str] = None
    for el in _tokens(h, parse_el):
        value = _value(h, el)
        if not value:
            continue
        valued += 1
        start = lowered.find(value.lower(), cursor)
        if start < 0:
            logger.debug("opsin_trace: token %r not found in %r after %d", value, text, cursor)
            if first_unfound is None:
                first_unfound = value
            continue
        span = (start, start + len(value))
        _write_span(h, el, TOKEN_TAG, span)
        written.append(WrittenToken(len(written), _name(h, el), value, span))
        cursor = span[1]
    if not written or len(written) < valued:
        # Any token that cannot be located means the written order and OPSIN's
        # parse order disagree (a reordered name): no partial trace.
        raise _Unplaceable(
            f"{valued - len(written)} of {valued} tokens of {text!r} could not be "
            f"located in it (first: {first_unfound!r})"
        )
    return written


def _stamp_parts(h, el) -> Optional[Span]:
    """R3. Every grouping element gets min..max of its non-stereo tokens --
    an identity key that clones inherit (see the module docstring)."""
    if _is_token(h, el):
        return _read_span(h, el, TOKEN_TAG)
    spans = []
    for child in _children(h, el):
        if _is_token(h, child) and _name(h, child) == STEREO_KIND:
            continue
        span = _stamp_parts(h, child)
        if span is not None:
            spans.append(span)
    if not spans:
        return None
    span = (min(a for a, _ in spans), max(b for _, b in spans))
    _write_span(h, el, PART_TAG, span)
    return span


# --------------------------------------------------------------------------
# 2. After ComponentProcessor: owners
# --------------------------------------------------------------------------

def _record_owners(h, parse_el, written: list[WrittenToken]) -> list[WrittenToken]:
    """Every non-stereo token still in the tree names the part OPSIN put it
    in. OPSIN may duplicate a token (hydro once per locant); copies share one
    span and one owner."""
    owners: dict[Span, Span] = {}
    for el in _tokens(h, parse_el):
        if _name(h, el) == STEREO_KIND:
            continue
        span = _read_span(h, el, TOKEN_TAG)
        if span is None:
            continue
        key = _owner_key(h, el)
        if key is not None:
            owners.setdefault(span, key)
    return [replace(tok, owner=owners.get(tok.span)) for tok in written]


# --------------------------------------------------------------------------
# 3. After the build
# --------------------------------------------------------------------------

def _collect_parts(h, parse_el, heavy: dict[int, int]) -> list[TracePart]:
    parts: list[TracePart] = []

    def atom_ids(el) -> list[int]:
        """Fragment atom ids under `el`, NOT descending into nested parts."""
        if _is_token(h, el):
            frag = h.get_frag.invoke(el)
            if frag is None:
                return []
            atoms = h.get_atom_list.invoke(frag)
            return [int(h.get_id.invoke(atoms.get(i))) for i in range(atoms.size())]
        ids: list[int] = []
        for child in _children(h, el):
            if not _is_token(h, child) and _name(h, child) in _PART_KINDS:
                continue
            ids.extend(atom_ids(child))
        return ids

    def walk(el, inherited: Optional[Span]) -> None:
        """`inherited` is the key of the nearest enclosing substituent/root
        that has one -- never a word's, a wordRule's or the molecule's, which
        would make unrelated parts share a key."""
        if _is_token(h, el):
            return
        name = _name(h, el)
        span = _read_span(h, el, PART_TAG)
        if name in _PART_KINDS:
            # A part OPSIN created after the parse has no key of its own; it
            # takes its nearest enclosing part's. With neither, it is unplaced.
            key = span if span is not None else inherited
            if key is None:
                raise _Unplaceable(f"a {name} has no key of its own and no enclosing part")
            locant = h.get_attribute_value.invoke(el, "locant")
            parts.append(TracePart(
                index=len(parts),
                kind=name,
                span=key,
                locant=None if locant is None else str(locant),
                atoms=tuple(sorted({heavy[i] for i in atom_ids(el) if i in heavy})),
            ))
            inherited = key
        for child in _children(h, el):
            walk(child, inherited)

    walk(parse_el, None)
    return parts


def _same_molecule(h, name: str, smiles: str) -> bool:
    try:
        public = h.nts.parseToSmiles(name)
    except SoftTimeLimitExceeded:
        raise
    except Exception:
        return False
    if public is None:
        return False
    a, b = Chem.MolFromSmiles(str(public)), Chem.MolFromSmiles(smiles)
    return a is not None and b is not None and Chem.MolToSmiles(a) == Chem.MolToSmiles(b)


def _trace_one(h, parse_el, text: str) -> tuple[Trace, bool]:
    """(the trace of one candidate parse, whether OPSIN's BuildState recorded a
    warning while building it)."""
    written = _stamp_tokens(h, parse_el, text)
    _stamp_parts(h, parse_el)
    state = h.state_ctor.newInstance(h.config)
    h.cg_process.invoke(h.cg_ctor.newInstance(state), parse_el)
    suffix_applier = h.sa_ctor.newInstance(state, h.suffix_rules)
    h.cp_process.invoke(h.cp_ctor.newInstance(state, suffix_applier), parse_el)
    written = _record_owners(h, parse_el, written)
    fragment = h.build_fragment.invoke(h.sb_ctor.newInstance(state), parse_el)
    warned = not bool(h.get_warnings.invoke(state).isEmpty())
    h.convert_spare_valencies.invoke(h.frag_manager_field.get(state))

    writer = h.sw_ctor.newInstance(fragment, h.default_smiles_opts)
    smiles = str(h.write_smiles.invoke(writer))
    order = h.output_order_field.get(writer)
    atoms = []
    heavy: dict[int, int] = {}
    for i in range(order.size()):
        atom = order.get(i)
        opsin_id = int(h.get_id.invoke(atom))
        locants = h.get_locants.invoke(atom)
        heavy[opsin_id] = i
        atoms.append(TraceAtom(
            index=i,
            opsin_id=opsin_id,
            element=str(h.get_atom_element.invoke(atom)),
            locants=tuple(str(locants.get(j)) for j in range(locants.size())),
        ))
    parts = _collect_parts(h, parse_el, heavy)
    if not parts:
        raise ValueError("no name parts recovered")
    return Trace(text, smiles, tuple(atoms), tuple(written), tuple(parts)), warned


def trace(name: str) -> Union[Trace, TraceFailure]:
    """Trace `name` through OPSIN. Mirrors NameToStructure.parseChemicalName:
    preprocess, parse, sort candidates "fewer tokens preferred", try each with
    a fresh BuildState (ComponentGenerator THROWS to reject a wrong candidate).
    """
    h = _get_handles()
    if h is None:
        return TraceFailure("unavailable")
    try:
        # OPSIN's Parser/SuffixRules are process-wide singletons with no
        # reentrancy guarantee: serialize the whole pipeline.
        with _lock:
            text = str(h.preprocess.invoke(None, name))
            parses = h.parse_method.invoke(h.parser, h.config, text)
            if parses.size() == 0:
                return TraceFailure("unreadable")
            candidates = [parses.get(i) for i in range(parses.size())]
            candidates.sort(key=cmp_to_key(lambda a, b: int(h.sort_parses.compare(a, b))))
            unplaced = False
            # NameToStructure.parseChemicalName returns the first candidate that
            # builds WITHOUT a BuildState warning; a candidate that builds with
            # one is only kept as a fallback ("diphenyl-λ5-phosphanonyl" reads
            # as phospha+nonyl first, with a warning, then as phosph+on+yl).
            warned_first: Optional[Trace] = None
            chosen: Optional[Trace] = None
            for parse_el in candidates:
                try:
                    result, warned = _trace_one(h, parse_el, text)
                except SoftTimeLimitExceeded:
                    raise
                except _Unplaceable as why:
                    logger.warning("opsin_trace: cannot place the parts of %r: %s", name, why)
                    unplaced = True
                    continue
                except Exception:
                    logger.debug("opsin_trace: candidate rejected for %r", name, exc_info=True)
                    continue
                if not warned:
                    chosen = result
                    break
                if warned_first is None:
                    warned_first = result
            chosen = chosen or warned_first
            if chosen is not None:
                if not _same_molecule(h, name, chosen.smiles):
                    logger.warning(
                        "opsin_trace: traced molecule for %r differs from OPSIN's "
                        "public parse -- rejecting", name,
                    )
                    return TraceFailure("mismatch")
                return chosen
            # A readable name whose parts cannot be placed is not "unreadable".
            return TraceFailure("unplaced" if unplaced else "unreadable")
    except SoftTimeLimitExceeded:
        raise
    except Exception:
        logger.debug("opsin_trace: OPSIN could not read %r", name, exc_info=True)
        return TraceFailure("unreadable")


# --------------------------------------------------------------------------
# JSON (fixtures for JVM-free tests)
# --------------------------------------------------------------------------

def trace_to_dict(t: Trace) -> dict:
    return asdict(t)


def _span(value) -> Optional[Span]:
    return None if value is None else (int(value[0]), int(value[1]))


def trace_from_dict(d: dict) -> Trace:
    return Trace(
        text=d["text"],
        smiles=d["smiles"],
        atoms=tuple(TraceAtom(a["index"], a["opsin_id"], a["element"], tuple(a["locants"]))
                    for a in d["atoms"]),
        tokens=tuple(WrittenToken(t["index"], t["kind"], t["value"], _span(t["span"]), _span(t["owner"]))
                     for t in d["tokens"]),
        parts=tuple(TracePart(p["index"], p["kind"], _span(p["span"]), p["locant"], tuple(p["atoms"]))
                    for p in d["parts"]),
    )
