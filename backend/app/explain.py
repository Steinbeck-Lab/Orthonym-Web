"""Name-to-structure explanation: decompose an Orthonym-generated name into
segments and map each one to real, RDKit-verified atoms wherever that
correspondence can be established reliably -- never guessed.

Design (the "honest hybrid", per product decision): suffix (principal
characteristic group) detection here is three-tier, most-authoritative
source first:

  1. PRIMARY: OPSIN's own tokenizer (opsin_tokenizer.find_suffix_span) --
     the same parser that turns a name INTO a structure, asked what it
     thinks each piece of the name actually IS, not a guess at how the
     rendered string happens to end. See opsin_tokenizer.py's module
     docstring for the full mechanism and its two confirmed real
     constraints (multi-word names, and why bare substituent fragments
     can't be independently resolved this way).
  2. SECONDARY: Orthonym's own name_with_tree() `suffix` field, when the
     tokenizer path above is unavailable (e.g. no JVM) or found nothing --
     a real, structured signal Orthonym already computed, though direct
     testing confirmed it collapses to an undecomposed "coarse_fallback"
     blob for a large class of real molecules (simple retained names like
     ethanol/acetic acid/acetamide, and ring/heterocycle names like
     benzene/caffeine's purine ring).
  3. TERTIARY: how the rendered NAME STRING ends -- IUPAC's own suffix-last
     composition order (P-14.5) makes this a legitimate last-resort signal,
     not a guess from nowhere, for whatever the two structured sources
     above still missed.

Whichever tier proposes a suffix class, it is NEVER trusted on its own: it
is only reported as a real segment when the corresponding SMARTS pattern
actually matches the real molecule via RDKit. "The name ends in -one" (or
"OPSIN's tokenizer tagged this token as a suffix") does not imply "this is
a ketone" -- caffeine's name ends in "-dione" but its two carbonyls sit
between ring nitrogens (amide-like), not between two carbons, and the
ketone SMARTS correctly fails to match; that molecule falls through to the
honest "could not decompose this name" case rather than shipping a wrong
highlight. Every tier proposes, SMARTS disposes -- this can only produce a
false negative (no segment reported), never a false positive (a wrong one).

The "rest of the molecule" (parent chain + any substituents) is never
sub-decomposed into individual named substituents. OPSIN's tokenizer DOES
mark real substituent/bracket boundaries in the name text, and Orthonym's
own substituent-prefix strings exist too, but turning either into further
real ATOM correspondences was confirmed, by direct testing, to require
resolving a bare substituent fragment (e.g. "phenyl", "methylpropyl") to
its own structure independently -- and OPSIN's top-level parser rejects a
bare substituent name (it expects a full parent+suffix name), so that
resolution would need OPSIN's non-public, substituent-specific grammar
entry points. Instead the "rest" segment is exactly the atom-index set
difference (total atoms minus the confirmed suffix atoms) -- a fact
derived from RDKit, not a guess, at the cost of not distinguishing "parent
chain" from "substituent" within it.
"""

from typing import NamedTuple, Optional

from rdkit import Chem
from rdkit.Chem.Draw import rdMolDraw2D

from orthonym import Orthonym

from . import opsin_substituents, opsin_tokenizer

_EXPLAIN_WIDTH = 340
_EXPLAIN_HEIGHT = 260

# Each rule: (tree.suffix values it matches, name-ending fallbacks, SMARTS,
# display name, plain-language explanation). Order matters only in that the
# first rule whose SMARTS actually matches wins -- checked in this order.
_SUFFIX_RULES = [
    (
        {"oic acid", "carboxylic acid"},
        ("oic acid", "carboxylic acid", "acid"),
        "[CX3](=O)[OX2H1]",
        "carboxylic acid",
        "This name ends in a carboxylic acid suffix. The highlighted "
        "-C(=O)OH group is what earns that ending.",
    ),
    (
        {"carbonitrile", "nitrile"},
        ("nitrile", "carbonitrile"),
        "[CX2]#[NX1]",
        "nitrile",
        "This name ends in a nitrile suffix. The highlighted -C≡N "
        "triple bond is what earns that ending.",
    ),
    (
        {"amide"},
        ("amide",),
        "[CX3](=O)[NX3]",
        "amide",
        "This name ends in an amide suffix. The highlighted "
        "-C(=O)N- group is what earns that ending.",
    ),
    (
        {"oate"},
        ("oate", "ate"),
        "[#6][CX3](=O)[OX2][#6]",
        "ester",
        "This name reads as an ester (two words, the second ending in "
        "-oate/-ate). The highlighted -C(=O)O- linkage is what earns "
        "that reading.",
    ),
    (
        {"al"},
        ("al", "aldehyde"),
        "[CX3H1](=O)[#6,H]",
        "aldehyde",
        "This name ends in an aldehyde suffix. The highlighted -CHO "
        "group is what earns that ending.",
    ),
    (
        {"one"},
        ("one",),
        "[#6][CX3](=O)[#6]",
        "ketone",
        "This name ends in a ketone suffix. The highlighted C=O, "
        "flanked by two carbons, is what earns that ending.",
    ),
    (
        {"amine"},
        ("amine",),
        "[NX3;!$(N-C=O);!$(N=*)]",
        "amine",
        "This name ends in an amine suffix. The highlighted nitrogen "
        "is what earns that ending.",
    ),
    (
        {"ol"},
        ("ol",),
        "[CX4][OX2H1]",
        "alcohol",
        "This name ends in an alcohol suffix. The highlighted -OH on "
        "a saturated carbon is what earns that ending.",
    ),
]


class SuffixMatch(NamedTuple):
    group_name: str
    explanation: str
    atom_indices: tuple[int, ...]
    source: str  # "tree" or "name-ending", for the API's transparency, not UI copy
    # How many trailing characters of `name` this suffix occupies, so the
    # frontend can visually pair the highlighted structure with the exact
    # substring of the name that names it (e.g. "prop" + "[anoic acid]").
    # None when that pairing can't be established as safely as the
    # structural match itself (kept separate from atom_indices so a
    # shaky name-range guess never gates a solid structural highlight).
    name_suffix_length: Optional[int]


def _find_suffix(name: str, tree, mol: Chem.Mol) -> Optional[SuffixMatch]:
    """Try OPSIN's own tokenizer first, then the tree's suffix field, then
    the name's ending. Returns None unless a SMARTS pattern actually
    confirms the match on the real molecule -- a suggested class that fails
    to match structurally is never reported, regardless of which tier
    proposed it.
    """
    span = opsin_tokenizer.find_suffix_span(name)
    if span is not None:
        suffix_text, start, end = span
        lower = suffix_text.lower()
        for _field_values, endings, smarts, group_name, explanation in _SUFFIX_RULES:
            if any(lower.endswith(ending) for ending in endings):
                match = _confirm(mol, smarts)
                if match is not None:
                    # The suffix span is, by IUPAC convention (P-14.5) and
                    # by every case seen in testing, the name's own trailing
                    # text -- confirm that literally before trusting `end`
                    # for the name-range pairing, same defensive pattern as
                    # the tree/name-ending tiers below.
                    length = len(name) - start if end == len(name) else None
                    return SuffixMatch(
                        group_name, explanation, match, "opsin-tokenizer", length
                    )
                # OPSIN's tokenizer identified a suffix-shaped token, but it
                # didn't confirm structurally -- same rule as the tree tier:
                # don't fall through to a different, coincidentally-matching
                # class from a lower tier. The tokenizer's signal is more
                # authoritative than a name-ending guess, so its failure to
                # confirm is reported as "undecomposed," not overridden.
                return None

    suffix_field = (tree.suffix if tree is not None else None)
    if suffix_field:
        norm = suffix_field.strip().lower()
        for field_values, _endings, smarts, group_name, explanation in _SUFFIX_RULES:
            if norm in field_values:
                match = _confirm(mol, smarts)
                if match is not None:
                    # The tree's suffix field should literally be the name's
                    # own trailing text (that's what Orthonym composed the
                    # name FROM) -- confirm it before using its length, so a
                    # mismatch just omits the name-range pairing rather than
                    # mis-slicing the string.
                    length = len(suffix_field) if name.lower().endswith(norm) else None
                    return SuffixMatch(group_name, explanation, match, "tree", length)
                # The tree said this suffix, but it didn't confirm on the
                # structure -- do not also try the name-ending fallback for
                # a DIFFERENT class; the tree's own signal takes priority
                # and its failure to confirm is reported as "undecomposed",
                # not silently overridden by a coincidental name-ending hit.
                return None

    lower_name = name.lower()
    for _field_values, endings, smarts, group_name, explanation in _SUFFIX_RULES:
        for ending in endings:
            if lower_name.endswith(ending):
                match = _confirm(mol, smarts)
                if match is not None:
                    return SuffixMatch(
                        group_name, explanation, match, "name-ending", len(ending)
                    )
    return None


def _confirm(mol: Chem.Mol, smarts: str) -> Optional[tuple[int, ...]]:
    pattern = Chem.MolFromSmarts(smarts)
    if pattern is None:
        return None
    matches = mol.GetSubstructMatches(pattern)
    if not matches:
        return None
    return tuple(sorted({atom for match in matches for atom in match}))


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


def explain_molecule(smiles: str, namer: Orthonym) -> dict:
    """Build an explanation for `smiles`, using `namer` (the SAME primary
    Orthonym instance /api/translate uses, for a consistent name) to name
    it. Returns a dict matching ExplainResponse's shape (see schemas.py).

    All atom indices refer to the SAME RDKit Mol used to render `svg` --
    parsed exactly once, so indices returned here are valid for `svg`'s
    atom-N / bond-N classes with no re-indexing.
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
    tree = tree_result.tree

    if not name or "unknown" in name.lower():
        return {
            "smiles": smiles,
            "name": None,
            "svg": None,
            "total_atoms": mol.GetNumAtoms(),
            "segments": [],
            "error": "Orthonym could not confidently name this molecule, so "
            "there is nothing to explain.",
        }

    svg = _inline_svg(mol)
    total_atoms = mol.GetNumAtoms()
    all_atoms = tuple(range(total_atoms))

    suffix_match = _find_suffix(name, tree, mol)

    segments = []
    if suffix_match is not None:
        rest_atoms = tuple(sorted(set(all_atoms) - set(suffix_match.atom_indices)))
        suffix_name_range = None
        rest_name_range = None
        if suffix_match.name_suffix_length is not None:
            split = len(name) - suffix_match.name_suffix_length
            suffix_name_range = [split, len(name)]
            if split > 0:
                rest_name_range = [0, split]
        segments.append(
            {
                "label": suffix_match.group_name,
                "kind": "suffix",
                "explanation": suffix_match.explanation,
                "atom_indices": list(suffix_match.atom_indices),
                "name_range": suffix_name_range,
            }
        )
        if rest_atoms:
            rest_atom_set = set(rest_atoms)
            claimed = set()
            for group in opsin_substituents.resolve_substituents(name, mol):
                group_atoms = set(group.atom_indices)
                # A suffix SMARTS pattern can claim a flanking atom that
                # structurally belongs to a named substituent (e.g. an
                # ester's "[#6][CX3](=O)[OX2][#6]" claims one carbon from
                # each side, including the "ethyl" group's own O-CH2 carbon
                # in "ethyl acetate"). Reporting the REMAINDER as if it were
                # the whole confirmed group would silently ship a partial,
                # sometimes-invisible highlight -- same "never a partial or
                # guessed result" rule this module already applies to
                # itself: only accept a group that survives intact.
                if (
                    not group_atoms
                    or not group_atoms.issubset(rest_atom_set)
                    or group_atoms & claimed
                ):
                    continue
                claimed |= group_atoms
                segments.append(
                    {
                        "label": group.label,
                        "kind": "substituent",
                        "explanation": f'The highlighted atoms are the "'
                        f'{group.label}" part of the name.',
                        "atom_indices": sorted(group_atoms),
                        "name_range": list(group.name_range)
                        if group.name_range is not None
                        else None,
                    }
                )
            unclaimed = sorted(rest_atom_set - claimed)
            if unclaimed:
                segments.append(
                    {
                        "label": "rest of the structure",
                        "kind": "rest",
                        "explanation": "The remaining carbon/ring skeleton "
                        "the name is built around. Orthonym's explainer "
                        "highlights it as one piece -- breaking it down "
                        "further isn't something it can currently do "
                        "reliably enough to show."
                        if not claimed
                        else "The remaining part of the structure not "
                        "covered by the named substituents above.",
                        "atom_indices": unclaimed,
                        "name_range": rest_name_range if not claimed else None,
                    }
                )
    else:
        segments.append(
            {
                "label": "whole structure",
                "kind": "undecomposed",
                "explanation": "Orthonym's explainer doesn't yet recognize a "
                "named part of this molecule it can confidently point to "
                "-- this can happen for retained/traditional names and for "
                "fused ring systems. Hovering highlights the whole "
                "structure instead of a guess at which part means what.",
                "atom_indices": list(all_atoms),
                "name_range": [0, len(name)],
            }
        )

    return {
        "smiles": smiles,
        "name": name,
        "svg": svg,
        "total_atoms": total_atoms,
        "segments": segments,
        "error": None,
    }
