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

from openstout import OpenSTOUT

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


def _inline_svg(mol: Chem.Mol) -> str:
    """Render `mol` as raw (non-data-URI) SVG markup with RDKit's default
    atom-N / bond-N CSS classes intact, so the frontend can style individual
    atoms/bonds on hover. Unlike depiction.py's data-URI helper, this is
    meant to be inlined directly into the page DOM, not used in an <img>.
    """
    drawer = rdMolDraw2D.MolDraw2DSVG(_EXPLAIN_WIDTH, _EXPLAIN_HEIGHT)
    drawer.DrawMolecule(mol)
    drawer.FinishDrawing()
    return drawer.GetDrawingText()


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


def _build_segments(result) -> list[dict]:
    by_index = {atom.rdkit_index: atom for atom in result.atoms}
    segments: list[dict] = []

    substituents = [p for p in result.parts if p.kind == "substituent"]
    grouped: dict[str, list] = {}
    for part in substituents:
        grouped.setdefault(part.text.strip("-"), []).append(part)

    for text, parts in grouped.items():
        children, owned = [], []
        for part in parts:
            atoms = heavy_atom_indices(result, part.opsin_atom_ids)
            owned.extend(atoms)
            if part.locant and atoms:
                element = by_index[atoms[0]].element
                children.append(
                    _segment(part.locant, "substituent",
                             describe_locant("substituent", part.locant, element),
                             atoms, locant=part.locant)
                )
        segments.append(
            _segment(text, "substituent",
                     describe_part("substituent", text, None, len(owned)),
                     owned, children=children)
        )

    for root in (p for p in result.parts if p.kind == "root"):
        split = split_root(result, root)
        parent_label = _parent_label(root)
        segments.append(
            _segment(parent_label, "parent",
                     describe_part("parent", parent_label, None,
                                   len(split.parent_atoms)),
                     split.parent_atoms)
        )
        if split.suffix_atoms:
            children = []
            for index in split.suffix_atoms:
                locant = split.suffix_locants.get(index)
                if locant is None:
                    continue
                highlight = [index] + [
                    i for i in split.parent_atoms
                    if locant in by_index[i].locants
                ]
                children.append(
                    _segment(locant, "suffix",
                             describe_locant("suffix", locant,
                                             by_index[index].element),
                             [index], locant=locant, highlight=highlight)
                )
            # The suffix's NAME comes from the root's own suffix tokens --
            # never a literal. Caffeine gives ("one", "one") -> "dione";
            # an alcohol gives ("ol",) -> "ol". Hardcoding "one" here would
            # tell an alcohol it has a C=O, which the never-guess rule forbids.
            texts = root.suffix_texts
            if texts and len(set(texts)) == 1 and len(texts) > 1:
                multiplier = {2: "di", 3: "tri", 4: "tetra"}.get(len(texts), "")
                suffix_label = f"{multiplier}{texts[0]}"
            else:
                suffix_label = "".join(dict.fromkeys(texts)) or "suffix"
            segments.append(
                _segment(suffix_label, "suffix",
                         describe_part("suffix", suffix_label, None,
                                       len(split.suffix_atoms)),
                         split.suffix_atoms, children=children)
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
            "smiles": "", "name": name, "svg": None, "total_atoms": 0,
            "segments": [],
            "error": "OPSIN could not parse this name.",
        }

    mol = Chem.MolFromSmiles(result.smiles)
    if mol is None:
        return {
            "smiles": result.smiles, "name": name, "svg": None,
            "total_atoms": 0, "segments": [],
            "error": "OPSIN parsed this name but the structure could not be read.",
        }

    return {
        "smiles": result.smiles,
        "name": name,
        "svg": _inline_svg(mol),
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
    sets = [
        frozenset(match[i] for i in indices if i < len(match))
        for match in matches
    ]
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


def explain_molecule(smiles: str, namer: OpenSTOUT) -> dict:
    """Build an explanation for `smiles`, using `namer` (the SAME primary
    OpenSTOUT instance /api/translate uses, for a consistent name) to name
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
            "total_atoms": mol.GetNumAtoms(),
            "segments": [],
            "error": "STITCH could not confidently name this molecule, so "
            "there is nothing to explain.",
        }

    svg = _inline_svg(mol)
    total_atoms = mol.GetNumAtoms()

    named = explain_name(name)
    if named["error"] is not None:
        return {
            "smiles": smiles,
            "name": name,
            "svg": svg,
            "total_atoms": total_atoms,
            "segments": [],
            "error": named["error"],
        }

    # `named`'s indices are into OPSIN's re-parse of the generated name, which
    # is a different Mol with its own atom order. Bridge the two by matching
    # that re-parse against the user's molecule.
    opsin_mol = Chem.MolFromSmiles(named["smiles"])
    matches: tuple = ()
    if opsin_mol is not None:
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
        "total_atoms": total_atoms,
        "segments": segments,
        "error": None,
    }
