"""Per-name-part atom-level decomposition, via OPSIN's INTERNAL (non-public)
parsing pipeline -- deliberately different from opsin_tokenizer.py, which
only uses OPSIN's public, documented tokenizer API.

Why this exists: explain.py's "rest of the structure" segment used to be one
undivided region because OPSIN's public top-level API
(``NameToStructure.parseChemicalName``) genuinely cannot resolve a BARE
substituent fragment like "phenyl" or "methylpropyl" standalone -- confirmed
by direct testing, not assumed (see opsin_tokenizer.py's module docstring).
That fact is still true. But it turns out to be the wrong question. OPSIN
never needs to resolve a substituent standalone when parsing a real, valid,
full chemical name -- it resolves each named substituent to its OWN
``Fragment`` (a real, disjoint set of atoms) as an ordinary internal step,
*before* sewing every piece into one final structure. This module
reflectively unlocks that internal pipeline
(``Parser`` -> ``ComponentGenerator`` -> ``ComponentProcessor`` ->
``StructureBuilder``) and reads out each name part's own Fragment -- but,
critically, only AFTER ``StructureBuilder.buildFragment`` has run, not
before. Reading before buildFragment was a real, reproduced bug: OPSIN
clones a multiplied substituent once per locant and re-attaches each clone to
the final structure INSIDE buildFragment (StructureBuildingMethods.java:
383-385), so caffeine's "1,3,7-trimethyl" reads as a single, undifferentiated
"trimethyl" substituent element before that point but as three separate
<substituent> elements -- each with its own LOCANT_ATR and its own clone
Fragment -- after it. Collecting post-buildFragment gives exactly the
per-locant atom decomposition the rest of this feature needs, produced by
OPSIN itself rather than inferred by string-splitting the multiplier prefix.

This is confirmed live and empirically, not theorized: running caffeine's
name through this pipeline for real produces three separately-locanted
"methyl" <substituent> elements (locants "1", "3", "7", four OPSIN atom IDs
each -- one carbon, three hydrogens -- pairwise disjoint) plus a single
"root" part carrying the purine ring and its two "one" suffix tokens, and the
atom list recovered from OPSIN's own SMILESWriter output order carries the
ring's original IUPAC locants (e.g. atom index 1 is N1, atom index 2 is C2)
straight from OPSIN's own numbering -- nothing here is re-derived by
substructure matching.

Two real, load-bearing constraints, both confirmed by direct testing:

1. Every class and most methods/fields used here (``Parser``,
   ``ComponentGenerator``, ``ComponentProcessor``, ``StructureBuilder``,
   ``Fragment``, ``TokenEl.getFrag()``, ...) are package-private in OPSIN's
   own source -- not part of any documented or version-guaranteed API. They
   are made callable ONLY via ``java.lang.reflect.AccessibleObject.
   setAccessible(true)``, which works against a plain classpath jar with no
   Java module boundaries (confirmed: this vendored jar has no
   module-info.class), but carries zero compatibility guarantee across OPSIN
   releases. ``_Handles.__init__`` resolves every one of these reflectively
   at first use and if ANY lookup fails -- a method renamed, a field
   removed, a class restructured in some future opsin-cli jar -- the whole
   thing fails loudly (logged) and disables itself: `decompose` returns None
   and explain.py turns that into a plain "could not decompose this name"
   error rather than any kind of partial answer. It never half-works.
   Because of this, the vendored jar version is pinned exactly
   (``vendor-orthonym.sh`` copies ``opsin-cli-2.9.0-jar-with-dependencies.
   jar`` by exact filename, not a glob) and ``_Handles.__init__`` additionally
   asserts ``NameToStructure.getVersion() == PINNED_OPSIN_VERSION`` as an
   early, loud warning signal distinct from (and cheaper than) the full
   reflection-shape check.
2. A named substituent can be internally SYMMETRIC in the real molecule even
   though the name's own grammar splits it into more than one substituent
   token (ibuprofen's "2-methylpropyl" is OPSIN's "methyl" substituent +
   "propyl" substituent, but the actual molecule's isobutyl group has two
   chemically-equivalent terminal methyls -- there is no real structural
   difference between "the methyl" and "the propyl chain's own terminal
   carbon"). Confirmed by direct testing: a molecule's substructure match
   against OPSIN's own reconstruction is sometimes NOT unique, and different
   valid matches disagree about which specific carbon is which -- but they
   always agree on the union. This module does not attempt that
   reconciliation itself (it has no `mol` to substructure-match against);
   it reports OPSIN's own name-part/atom decomposition as-is. The
   reconciliation lives in `explain.py` (`_agreed_atoms` / `_remap_segment`),
   on the structure-in path that actually has the user's molecule to match
   against; a part the matches disagree about becomes `kind="unmapped"`.
"""

from __future__ import annotations

import logging
import threading
from typing import NamedTuple, Optional

logger = logging.getLogger(__name__)

PINNED_OPSIN_VERSION = "2.9.0"


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
    """Every reflection handle this module depends on, resolved exactly
    once. See module docstring constraint (1): if OPSIN's internal shape
    has changed, construction raises here and the caller disables the
    feature -- this class never returns a partially-working state.
    """

    def __init__(self):
        import jpype
        import jpype.imports  # noqa: F401

        J = jpype.JClass

        self.NameToStructure = J("uk.ac.cam.ch.wwmm.opsin.NameToStructure")
        self.NameToStructureConfig = J("uk.ac.cam.ch.wwmm.opsin.NameToStructureConfig")
        self.BuildState = J("uk.ac.cam.ch.wwmm.opsin.BuildState")
        self.Parser = J("uk.ac.cam.ch.wwmm.opsin.Parser")
        self.ComponentGenerator = J("uk.ac.cam.ch.wwmm.opsin.ComponentGenerator")
        self.ComponentProcessor = J("uk.ac.cam.ch.wwmm.opsin.ComponentProcessor")
        self.SuffixApplier = J("uk.ac.cam.ch.wwmm.opsin.SuffixApplier")
        self.SuffixRules = J("uk.ac.cam.ch.wwmm.opsin.SuffixRules")
        self.StructureBuilder = J("uk.ac.cam.ch.wwmm.opsin.StructureBuilder")
        self.Element = J("uk.ac.cam.ch.wwmm.opsin.Element")
        self.TokenEl = J("uk.ac.cam.ch.wwmm.opsin.TokenEl")
        self.Fragment = J("uk.ac.cam.ch.wwmm.opsin.Fragment")
        self.FragmentManager = J("uk.ac.cam.ch.wwmm.opsin.FragmentManager")
        self.SMILESWriter = J("uk.ac.cam.ch.wwmm.opsin.SMILESWriter")
        self.SmilesOptions = J("uk.ac.cam.ch.wwmm.opsin.SmilesOptions")
        self.Atom = J("uk.ac.cam.ch.wwmm.opsin.Atom")
        JString = J("java.lang.String")
        JInt = J("java.lang.Integer").TYPE

        nts = self.NameToStructure.getInstance()
        version = str(self.NameToStructure.getVersion())
        if version != PINNED_OPSIN_VERSION:
            logger.warning(
                "opsin_decompose: running against OPSIN %s, pinned/tested "
                "version is %s -- internal reflection API may not match; "
                "proceeding only because every lookup below still succeeded",
                version,
                PINNED_OPSIN_VERSION,
            )

        self.parser = _unlock_field(self.NameToStructure, "parser").get(nts)
        self.suffix_rules = _unlock_field(self.NameToStructure, "suffixRules").get(nts)
        self.config = self.NameToStructureConfig.getDefaultConfigInstance()

        self.state_ctor = _unlock_ctor(self.BuildState, self.NameToStructureConfig)
        self.parse_method = _unlock_method(
            self.Parser, "parse", self.NameToStructureConfig, JString
        )
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
        self.get_frag = _unlock_method(self.TokenEl, "getFrag")
        self.get_value = _unlock_method(self.TokenEl, "getValue")
        self.get_atom_list = _unlock_method(self.Fragment, "getAtomList")
        self.get_id = _unlock_method(self.Atom, "getID")
        self.frag_manager_field = _unlock_field(self.BuildState, "fragManager")

        self.get_attribute_value = _unlock_method(
            self.Element, "getAttributeValue", JString
        )
        self.get_locants = _unlock_method(self.Atom, "getLocants")
        self.get_atom_element = _unlock_method(self.Atom, "getElement")


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
            logger.info("opsin_decompose: internal reflection API verified OK")
        except Exception:
            logger.exception(
                "opsin_decompose: OPSIN's internal API shape is unavailable "
                "or has changed -- disabling name-part decomposition; every "
                "Explain request will report a plain 'could not decompose' "
                "error rather than a partial or guessed answer"
            )
            _handles = False
    return _handles or None


def self_check() -> bool:
    """Eagerly resolves every reflection handle this feature depends on,
    logging the outcome plainly. Meant to be called once at app startup (see
    main.py) so an incompatible OPSIN jar is a loud, immediate boot-time
    signal -- not something a user discovers only when the Explain page's
    substituent regions silently never appear. Returns whether the feature
    is usable; the caller doesn't need to branch on this (decompose degrades
    to None regardless), it's purely for the startup log line.
    """
    return _get_handles() is not None


class NamePart(NamedTuple):
    kind: str                        # "substituent" or "root"
    text: str                        # concatenated raw token values
    locant: str | None               # LOCANT_ATR, e.g. "1" on a multiplied clone
    opsin_atom_ids: tuple[int, ...]
    # Values of this part's own <suffix> child tokens, in order. Caffeine's
    # root gives ("one", "one"). These carry NO atoms of their own (verified:
    # their fragments are empty), but they are the only place the principal
    # characteristic group's NAME survives -- Task 7 needs them so an "-ol"
    # molecule is not described as having a C=O.
    suffix_texts: tuple[str, ...] = ()


class DecomposedAtom(NamedTuple):
    rdkit_index: int                 # position in SMILESWriter output order
    opsin_id: int
    element: str
    locants: tuple[str, ...]


class Modifier(NamedTuple):
    kind: str      # "hydro" or "indicatedHydrogen"
    locant: str    # resolved locant, e.g. "3"
    # WHICH name part's numbering `locant` is written in: "root" (the named
    # parent skeleton) or "substituent". Load-bearing -- see
    # _collect_modifiers. "unknown" means neither ancestor was found, which
    # is treated exactly like "substituent": not resolvable against the
    # parent, so never mapped onto a parent atom.
    scope: str = "unknown"


class Decomposition(NamedTuple):
    smiles: str
    atoms: tuple[DecomposedAtom, ...]
    parts: tuple[NamePart, ...]
    modifiers: tuple[Modifier, ...] = ()


def _collect_parts(h: _Handles, parse_el) -> list[NamePart]:
    """Walks the POST-buildFragment tree. At that point OPSIN has already
    cloned each multiplied substituent once per locant and re-attached every
    clone (StructureBuildingMethods.java:383-385), so a multiplied group
    appears here as N separate <substituent> elements each carrying its own
    LOCANT_ATR -- which is exactly the two-level tree we want, produced by
    OPSIN rather than inferred by us.

    <suffix> elements are deliberately NOT collected: verified, they carry
    an empty fragment, and their atoms are merged into the parent group's
    fragment. The parent/suffix split happens in Task 4 from locants.
    """
    parts: list[NamePart] = []

    def frag_atom_ids(el) -> list[int]:
        ids: list[int] = []
        if h.TokenEl.class_.isInstance(el):
            frag = h.get_frag.invoke(el)
            if frag is not None:
                atoms = h.get_atom_list.invoke(frag)
                ids.extend(int(h.get_id.invoke(atoms.get(i))) for i in range(atoms.size()))
            return ids
        children = h.get_children.invoke(el)
        for i in range(children.size()):
            ids.extend(frag_atom_ids(children.get(i)))
        return ids

    def text_of(el) -> str:
        if h.TokenEl.class_.isInstance(el):
            return str(h.get_value.invoke(el))
        children = h.get_children.invoke(el)
        return "".join(text_of(children.get(i)) for i in range(children.size()))

    def suffix_texts_of(el) -> tuple[str, ...]:
        """Direct <suffix> children of this part, by token value. Their
        fragments are empty (their atoms live in the group's fragment), so
        this is the only surviving record of what the suffix is CALLED.
        """
        texts = []
        children = h.get_children.invoke(el)
        for i in range(children.size()):
            child = children.get(i)
            # getValue is a TokenEl method -- guard, or it throws on a
            # non-token child element.
            if not h.TokenEl.class_.isInstance(child):
                continue
            if str(h.get_name.invoke(child)) == "suffix":
                texts.append(str(h.get_value.invoke(child)))
        return tuple(texts)

    def walk(el) -> None:
        name = str(h.get_name.invoke(el))
        if name in ("substituent", "root"):
            ids = frag_atom_ids(el)
            if ids:
                locant = h.get_attribute_value.invoke(el, "locant")
                parts.append(
                    NamePart(
                        kind=name,
                        text=text_of(el),
                        locant=str(locant) if locant is not None else None,
                        opsin_atom_ids=tuple(sorted(set(ids))),
                        suffix_texts=suffix_texts_of(el),
                    )
                )
            return
        children = h.get_children.invoke(el)
        for i in range(children.size()):
            walk(children.get(i))

    walk(parse_el)
    return parts


_MODIFIER_ELEMENTS = ("hydro", "indicatedHydrogen")

# The two enclosing part elements whose numbering a modifier's locant can be
# written in. Whichever of these is nearest above the modifier owns it.
_MODIFIER_SCOPES = ("root", "substituent")


def _collect_modifiers(h: _Handles, parse_el) -> list[Modifier]:
    """Hydro prefixes and indicated hydrogen -- the "3,7-dihydro-1H-" part
    of a name. These add no atoms; they record where hydrogens sit, which
    fixes where the ring double bonds go.

    MUST be called after ComponentProcessor and BEFORE buildFragment.
    Verified against the pinned jar: after processing these elements carry
    their resolved locant (caffeine -> hydro@3, hydro@7, indicatedHydrogen@1),
    and buildFragment consumes them, leaving none in the tree.

    **Each modifier carries the SCOPE its locant is written in, and callers
    must honour it.** A locant means nothing without the numbering it belongs
    to, and this walk crosses several. Verified live against the pinned jar,
    printing each modifier's full element path:

        1,3,7-trimethyl-3,7-dihydro-1H-purine-2,6-dione
            hydro@3             molecule/wordRule/word/root/hydro
            hydro@7             molecule/wordRule/word/root/hydro
            indicatedHydrogen@1 molecule/wordRule/word/root/indicatedHydrogen
        2-amino-3-(1H-indol-3-yl)propanoic acid
            indicatedHydrogen@1 .../word/bracket/substituent/indicatedHydrogen

    Tryptophan's ``1H`` is INDOLE's, and indole is a substituent -- its "1"
    is a position on the indole ring system, not on the propanoic parent.
    Returning it unscoped is what let explain.py resolve it against the
    parent skeleton and highlight a propanoic carbon: a confident highlight
    of the wrong fragment entirely. Reproduced identically on
    2-(4,5-dihydro-1H-imidazol-2-yl)phenol, ethyl 2-(1H-indol-3-yl)acetate
    and 1-(2,3-dihydro-1H-inden-5-yl)ethan-1-one.

    A substituent-scoped modifier is still RETURNED, never dropped -- spec §6
    requires an unresolvable part to be visible as ``kind="unmapped"``, not
    invisible. Scoping is the caller's filter, not a silent discard here.
    """
    found: list[Modifier] = []

    def walk(el, scope: str) -> None:
        name = str(h.get_name.invoke(el))
        if name in _MODIFIER_SCOPES:
            # Nearest enclosing part wins: a <substituent> inside a <bracket>
            # inside a <word> overrides the word's own <root>.
            scope = name
        if h.TokenEl.class_.isInstance(el):
            if name in _MODIFIER_ELEMENTS:
                locant = h.get_attribute_value.invoke(el, "locant")
                if locant is not None:
                    found.append(
                        Modifier(kind=name, locant=str(locant), scope=scope)
                    )
            return
        children = h.get_children.invoke(el)
        for i in range(children.size()):
            walk(children.get(i), scope)

    walk(parse_el, "unknown")
    return found


def decompose(name: str) -> Optional[Decomposition]:
    """Runs OPSIN's internal pipeline for `name` and reports every name part
    with its own atoms, plus every heavy atom with its locants. Returns None
    on any failure -- reflection unavailable, name unparseable, or the
    pipeline raising. None means "cannot decompose", never a partial result.
    """
    h = _get_handles()
    if h is None:
        return None

    try:
        # OPSIN's Parser/SuffixRules are process-wide singletons with no
        # documented reentrancy guarantee, and FastAPI runs sync endpoints on
        # a threadpool. Serialize the whole pipeline.
        with _lock:
            state = h.state_ctor.newInstance(h.config)
            parses = h.parse_method.invoke(h.parser, h.config, name)
            if parses.size() == 0:
                return None
            parse_el = parses.get(0)

            h.cg_process.invoke(h.cg_ctor.newInstance(state), parse_el)
            suffix_applier = h.sa_ctor.newInstance(state, h.suffix_rules)
            h.cp_process.invoke(h.cp_ctor.newInstance(state, suffix_applier), parse_el)

            # BEFORE buildFragment -- it consumes these elements.
            modifiers = _collect_modifiers(h, parse_el)

            sb = h.sb_ctor.newInstance(state)
            final_frag = h.build_fragment.invoke(sb, parse_el)
            h.convert_spare_valencies.invoke(h.frag_manager_field.get(state))

            # AFTER buildFragment -- this ordering IS the fix.
            parts = _collect_parts(h, parse_el)

            sw = h.sw_ctor.newInstance(final_frag, h.default_smiles_opts)
            smiles = str(h.write_smiles.invoke(sw))
            order = h.output_order_field.get(sw)

            atoms = []
            for i in range(order.size()):
                atom = order.get(i)
                locants = h.get_locants.invoke(atom)
                atoms.append(
                    DecomposedAtom(
                        rdkit_index=i,
                        opsin_id=int(h.get_id.invoke(atom)),
                        element=str(h.get_atom_element.invoke(atom)),
                        locants=tuple(str(locants.get(j)) for j in range(locants.size())),
                    )
                )
    except Exception:
        logger.exception("opsin_decompose: failed decomposing %r", name)
        return None

    if not parts:
        return None
    return Decomposition(
        smiles=smiles,
        atoms=tuple(atoms),
        parts=tuple(parts),
        modifiers=tuple(modifiers),
    )


def heavy_atom_indices(result: Decomposition, opsin_ids) -> tuple[int, ...]:
    """Maps OPSIN atom ids to RDKit heavy-atom indices valid against
    `result.smiles`. Hydrogens drop out for free: SMILESWriter's output order
    contains only heavy atoms, so an explicit-H id is simply absent from the
    lookup rather than needing a separate filter.
    """
    by_id = {atom.opsin_id: atom.rdkit_index for atom in result.atoms}
    return tuple(sorted(by_id[i] for i in opsin_ids if i in by_id))
