"""Per-substituent atom-level decomposition, via OPSIN's INTERNAL (non-public)
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
*before* stitching every piece into one final structure. This module
reflectively unlocks that internal pipeline
(``Parser`` -> ``ComponentGenerator`` -> ``ComponentProcessor`` ->
``StructureBuilder``) and reads out each substituent's own Fragment at the
point where it's still separate -- never asking OPSIN to parse a fragment in
isolation, only asking it what it already privately knows mid-way through a
parse that succeeds.

This is confirmed live and empirically, not theorized: running ibuprofen's
generated name through this pipeline for real produces three distinct
per-substituent atom sets ("methyl", "propyl", "phenyl") plus the parent
chain+suffix, and bridging those OPSIN-internal atom IDs back to the
ORIGINAL molecule's RDKit atom indices (via OPSIN's own SMILESWriter output
order, then a whole-molecule substructure match against the original SMILES)
reproduces the exact expected atom groups.

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
   thing fails loudly (logged) and disables itself, falling back to
   explain.py's existing undivided "rest" segment. It never half-works.
   Because of this, the vendored jar version is pinned exactly
   (``vendor-openstout.sh`` copies ``opsin-cli-2.9.0-jar-with-dependencies.
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
   always agree on the union. `_resolve_confirmed_groups` handles this
   explicitly: an individual substituent is only reported if EVERY valid
   match agrees on its atom set; disagreeing adjacent substituents are
   merged into one region and re-checked; a region that still disagrees
   after merging is dropped (its atoms simply stay in the caller's
   undecomposed "rest" bucket) rather than picking an arbitrary side of a
   real symmetry.
"""

from __future__ import annotations

import logging
import threading
from typing import NamedTuple, Optional

from rdkit import Chem

logger = logging.getLogger(__name__)

PINNED_OPSIN_VERSION = "2.9.0"

# Generous headroom above what any realistically-drawn small molecule's
# automorphism count needs, so the cap is essentially never hit by a
# genuine case -- see the cap-hit check in resolve_substituents for why
# hitting it must mean "inconclusive," never "confirmed."
_MAX_SUBSTRUCT_MATCHES = 4096


class SubstituentGroup(NamedTuple):
    label: str
    atom_indices: tuple[int, ...]  # into the ORIGINAL RDKit mol
    name_range: Optional[tuple[int, int]]  # [start, end) into the original name


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
                "opsin_substituents: running against OPSIN %s, pinned/tested "
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
            from openstout.jvm_bridge import opsin_available

            if not opsin_available():
                _handles = False
                return None
            _handles = _Handles()
            logger.info("opsin_substituents: internal reflection API verified OK")
        except Exception:
            logger.exception(
                "opsin_substituents: OPSIN's internal API shape is unavailable "
                "or has changed -- disabling substituent decomposition, "
                "falling back to the undivided 'rest of structure' segment"
            )
            _handles = False
    return _handles or None


def self_check() -> bool:
    """Eagerly resolves every reflection handle this feature depends on,
    logging the outcome plainly. Meant to be called once at app startup (see
    main.py) so an incompatible OPSIN jar is a loud, immediate boot-time
    signal -- not something a user discovers only when the Explain page's
    substituent regions silently never appear. Returns whether the feature
    is usable; the caller doesn't need to branch on this (resolve_substituents
    degrades to [] regardless), it's purely for the startup log line.
    """
    return _get_handles() is not None


class _Candidate:
    __slots__ = ("label", "opsin_ids")

    def __init__(self, label: str, opsin_ids: frozenset):
        self.label = label
        self.opsin_ids = opsin_ids


def _collect_candidates(h: _Handles, parse_el) -> list:
    """Walks the post-ComponentProcessor tree in document order, returning
    one _Candidate per top-level <substituent> element found anywhere in the
    tree (a substituent may itself contain more than one <group> token, e.g.
    a locanted multi-word substituent -- all of that substituent's own group
    atoms are unioned into one candidate).
    """
    candidates = []

    def group_atoms_in_subtree(el) -> tuple:
        ids = []
        if h.TokenEl.class_.isInstance(el):
            frag = h.get_frag.invoke(el)
            if frag is not None:
                atoms = h.get_atom_list.invoke(frag)
                ids = [int(h.get_id.invoke(atoms.get(i))) for i in range(atoms.size())]
            return ids
        children = h.get_children.invoke(el)
        for i in range(children.size()):
            ids.extend(group_atoms_in_subtree(children.get(i)))
        return ids

    def label_in_subtree(el) -> str:
        if h.TokenEl.class_.isInstance(el):
            return str(h.get_value.invoke(el))
        children = h.get_children.invoke(el)
        return "".join(label_in_subtree(children.get(i)) for i in range(children.size()))

    def walk(el):
        name = str(h.get_name.invoke(el))
        if name == "substituent":
            ids = group_atoms_in_subtree(el)
            if ids:
                candidates.append(_Candidate(label_in_subtree(el), frozenset(ids)))
            return  # a <substituent> is never nested inside another <substituent>
        children = h.get_children.invoke(el)
        for i in range(children.size()):
            walk(children.get(i))

    walk(parse_el)
    return candidates


def _resolve_confirmed_groups(candidates: list, matches: list, opsin_order_ids: list) -> list:
    """Maps each candidate's OPSIN atom-ID set through every substructure
    match; keeps it only if every match agrees on the resulting atom-index
    set (module docstring constraint 2). Adjacent candidates that disagree
    are merged into one region and re-checked once; still-disputed regions
    are dropped, not guessed.
    """
    id_to_idx_per_match = [
        {opsin_order_ids[i]: match[i] for i in range(len(match))} for match in matches
    ]

    def mapped_sets(ids):
        return [frozenset(m[i] for i in ids if i in m) for m in id_to_idx_per_match]

    def agrees(ids):
        sets = mapped_sets(ids)
        return sets and all(s == sets[0] for s in sets)

    confirmed = []
    disputed_run = []

    def flush_run():
        if not disputed_run:
            return
        merged_ids = frozenset().union(*(c.opsin_ids for c in disputed_run))
        if agrees(merged_ids):
            merged_label = "".join(c.label for c in disputed_run)
            confirmed.append((merged_label, merged_ids))
        disputed_run.clear()

    for cand in candidates:
        if agrees(cand.opsin_ids):
            flush_run()
            confirmed.append((cand.label, cand.opsin_ids))
        else:
            disputed_run.append(cand)
    flush_run()

    out = []
    for label, ids in confirmed:
        mapped = mapped_sets(ids)[0]
        out.append((label, mapped))
    return out


def resolve_substituents(name: str, mol: Chem.Mol) -> list[SubstituentGroup]:
    """Best-effort per-substituent atom decomposition for `name` against the
    ORIGINAL `mol`. Returns [] on ANY failure -- reflection unavailable, this
    particular name's grammar not covered, no structural match, or an
    inconsistent/symmetric result that can't be honestly assigned. An empty
    list is the correct, safe outcome for explain.py to treat exactly like
    "nothing more to decompose", never a partial or guessed result.
    """
    h = _get_handles()
    if h is None:
        return []

    try:
        # OPSIN's own Parser/SuffixRules objects (h.parser, h.suffix_rules)
        # are process-wide singletons reused across every call -- there's no
        # documented guarantee they (or the ComponentGenerator/
        # ComponentProcessor/StructureBuilder instances created from them)
        # are safe under concurrent use, and FastAPI's sync endpoints run on
        # a threadpool. Serialize the whole reflective pipeline rather than
        # assume reentrancy that was never confirmed; this feature isn't a
        # hot path, so correctness is worth more here than concurrency.
        with _lock:
            state = h.state_ctor.newInstance(h.config)
            parses = h.parse_method.invoke(h.parser, h.config, name)
            if parses.size() == 0:
                return []
            parse_el = parses.get(0)

            cg = h.cg_ctor.newInstance(state)
            h.cg_process.invoke(cg, parse_el)

            suffix_applier = h.sa_ctor.newInstance(state, h.suffix_rules)
            cp = h.cp_ctor.newInstance(state, suffix_applier)
            h.cp_process.invoke(cp, parse_el)

            candidates = _collect_candidates(h, parse_el)
            if not candidates:
                return []

            sb = h.sb_ctor.newInstance(state)
            final_frag = h.build_fragment.invoke(sb, parse_el)

            frag_manager = h.frag_manager_field.get(state)
            h.convert_spare_valencies.invoke(frag_manager)

            sw = h.sw_ctor.newInstance(final_frag, h.default_smiles_opts)
            smiles = str(h.write_smiles.invoke(sw))
            output_order = h.output_order_field.get(sw)
            opsin_order_ids = [
                int(h.get_id.invoke(output_order.get(i))) for i in range(output_order.size())
            ]

        opsin_mol = Chem.MolFromSmiles(smiles)
        if opsin_mol is None or opsin_mol.GetNumAtoms() != len(opsin_order_ids):
            return []

        matches = mol.GetSubstructMatches(opsin_mol, uniquify=False, maxMatches=_MAX_SUBSTRUCT_MATCHES)
        if not matches:
            return []
        if len(matches) >= _MAX_SUBSTRUCT_MATCHES:
            # The consistency check below only proves anything if we've seen
            # EVERY automorphism -- a molecule symmetric enough to hit this
            # cap could have an unseen automorphism that disagrees with the
            # ones we did see, which is exactly the "arbitrary side of a
            # real symmetry" outcome this feature exists to avoid. Treat a
            # capped enumeration as inconclusive, not confirmed.
            logger.warning(
                "opsin_substituents: substructure match count hit the cap "
                "(%d) for %r -- too symmetric to prove consistency, "
                "skipping decomposition for this molecule",
                _MAX_SUBSTRUCT_MATCHES,
                name,
            )
            return []

        resolved = _resolve_confirmed_groups(candidates, matches, opsin_order_ids)
    except Exception:
        logger.exception(
            "opsin_substituents: failed decomposing %r -- falling back to "
            "the undivided 'rest of structure' segment for this molecule",
            name,
        )
        return []

    groups = []
    search_from = 0
    for raw_label, atom_indices in resolved:
        if not atom_indices:
            continue
        # A substituent-prefix token (e.g. "chloro") sometimes carries the
        # locant-separator hyphen that follows it in the name text (e.g.
        # "chloro-" in "3-chloro-4-methyl...") as part of its own token
        # value -- strip it, it's name punctuation, not part of the
        # chemical word being highlighted.
        label = raw_label.strip("-")
        name_range = None
        idx = name.find(label, search_from)
        if idx != -1:
            name_range = (idx, idx + len(label))
            search_from = idx + len(label)
        groups.append(
            SubstituentGroup(
                label=label,
                atom_indices=tuple(sorted(atom_indices)),
                name_range=name_range,
            )
        )
    return groups
