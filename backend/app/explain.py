"""Name-to-structure explanation: decompose an IUPAC name into a two-level
tree of parts and map each part to the real atoms it names.

The design, the evidence behind it and the failure policy live in the spec:
``docs/superpowers/specs/2026-08-14-explain-iupac-decomposition-design.md``.
The short version, because it governs everything below:

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

from orthonym import Orthonym

from .glossary import describe_locant, describe_part
from .opsin_decompose import decompose, heavy_atom_indices
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


def _locant_sort_key(segment: dict):
    locant = segment.get("locant") or ""
    digits = "".join(c for c in locant if c.isdigit())
    return (int(digits) if digits else 0, locant)


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
        names_its_suffix = bool(root.suffix_texts)
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
            "error": "OPSIN could not parse this name.",
        }

    mol = Chem.MolFromSmiles(result.smiles)
    if mol is None:
        return {
            "smiles": result.smiles, "name": name, "svg": None, "atom_points": [],
            "total_atoms": 0, "segments": [],
            "error": "OPSIN parsed this name but the structure could not be read.",
        }

    svg, atom_points = _inline_svg(mol)
    return {
        "smiles": result.smiles,
        "name": name,
        "svg": svg,
        "atom_points": atom_points,
        "total_atoms": mol.GetNumAtoms(),
        "segments": _build_segments(result),
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


def explain_molecule(smiles: str, namer: Orthonym) -> dict:
    """Build an explanation for `smiles`, using `namer` (the SAME primary
    Orthonym instance /api/translate uses, for a consistent name) to name
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
            "error": "Orthonym could not confidently name this molecule, so "
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
            "explain: the name Orthonym generated (%r) re-parses to %d heavy "
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
