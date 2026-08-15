"""Plain-language descriptions of name parts, composed deterministically.

Two rules, both load-bearing:
  1. Text is looked up, never generated. Same input, same output, forever.
  2. A part with no glossary entry gets a NEUTRAL FACTUAL line stating what
     it is called and how many atoms it covers -- never invented chemistry.
     Being uninformative is acceptable; being confidently wrong is not.
"""

from __future__ import annotations

# Morpheme -> what it is, in plain words. Keys are OPSIN's own token values
# (the raw stem, e.g. "meth" + "yl" -> looked up as "methyl").
_SUBSTITUENTS = {
    "methyl": "a CH3 group — one carbon with three hydrogens",
    "ethyl": "a CH3-CH2- group — two carbons",
    "propyl": "a three-carbon chain",
    "butyl": "a four-carbon chain",
    "phenyl": "a benzene ring attached by one of its carbons",
    "chloro": "a chlorine atom",
    "bromo": "a bromine atom",
    "fluoro": "a fluorine atom",
    "iodo": "an iodine atom",
    "nitro": "an -NO2 group",
    "amino": "an -NH2 group",
    "hydroxy": "an -OH group",
    "acetyloxy": "an -O-C(=O)-CH3 group",
    "methoxy": "an -O-CH3 group",
    "ethoxy": "an -O-CH2CH3 group",
    "acetyl": "a CH3-C(=O)- group",
    "indolyl": "an indole ring system attached by one of its carbons",
    "oxy": "an -O- linkage joining two parts of the name",
}

_SUFFIXES = {
    "one": "a C=O group (a carbonyl)",
    "ol": "an -OH group",
    "al": "a -CHO group",
    "amine": "a nitrogen with free hydrogens",
    "amide": "a -C(=O)N- group",
    "nitrile": "a -C≡N triple bond",
    # Order matters: _lookup falls back to endswith, so the MORE SPECIFIC
    # acid endings must come first. "propanoic acid" ends with both
    # "oic acid" and "ic acid"; the first match wins.
    "oic acid": "a -C(=O)OH group",
    "carboxylic acid": "a -C(=O)OH group",
    "ic acid": "a -C(=O)OH group",
    "oate": "an ester -C(=O)O- linkage",
    "ate": "an ester -C(=O)O- linkage",
}

# Parent skeleton stems, as OPSIN's <group> token spells them. Verified live
# against the pinned jar -- these are the exact values the parent label
# derivation in explain.py produces, not guesses at spelling.
_PARENTS = {
    "purin": "purine — two fused rings holding four nitrogens",
    "benzen": "benzene — a six-carbon aromatic ring",
    "benz": "a benzene ring",
    "indol": "indole — a benzene ring fused to a five-membered nitrogen ring",
    "pyridin": "pyridine — a six-membered ring with one nitrogen",
    "naphthalen": "naphthalene — two fused benzene rings",
    "meth": "a one-carbon skeleton",
    "eth": "a two-carbon skeleton",
    "prop": "a three-carbon skeleton",
    "but": "a four-carbon skeleton",
    "pent": "a five-carbon skeleton",
    "hex": "a six-carbon skeleton",
    "hept": "a seven-carbon skeleton",
    "oct": "an eight-carbon skeleton",
    "acet": "a two-carbon acetyl skeleton",
}

_MULTIPLIERS = {
    "di": "two of them",
    "tri": "three of them",
    "tetra": "four of them",
    "penta": "five of them",
    "hexa": "six of them",
}


def _lookup(table: dict, text: str) -> str | None:
    key = text.strip("-").lower()
    if key in table:
        return table[key]
    for name, description in table.items():
        if key.endswith(name):
            return description
    return None


def describe_part(kind: str, text: str, locant: str | None, atom_count: int) -> str:
    label = text.strip("-")
    where = f" It sits at position {locant}." if locant else ""

    if kind == "substituent":
        known = _lookup(_SUBSTITUENTS, label)
        if known:
            return f'"{label}" is {known}.{where}'
    elif kind == "suffix":
        known = _lookup(_SUFFIXES, label)
        if known:
            return f'The "{label}" ending means {known}.{where}'
    elif kind == "parent":
        known = _PARENTS.get(label.lower())
        if known:
            return (
                f'"{label}" is {known}. It is the core the rest of the name '
                f"is built around, and it holds {atom_count} atoms."
            )
        return (
            f'"{label}" is the core skeleton the rest of the name is built '
            f"around. It has {atom_count} atoms."
        )
    elif kind == "modifier":
        return (
            f'"{label}" does not add atoms. It records where hydrogens sit, '
            f"which fixes where the double bonds go."
        )
    elif kind == "unmapped":
        return (
            f'"{label}" is part of this name, but Orthonym could not work out '
            f"which atoms it refers to. The other parts are unaffected."
        )

    plural = "atom" if atom_count == 1 else "atoms"
    return f'"{label}" covers {atom_count} {plural} of this structure.{where}'


def describe_locant(kind: str, locant: str, element: str | None = None) -> str:
    """One line for a CHILD segment, which is identified only by its locant.

    `element` names an atom in the sentence, so there is exactly one rule
    about it and it is not negotiable: **pass it only when the caller has
    resolved the real atom that carries this locant, in the numbering the
    locant is written in.** Anything else fabricates an atom label.

    Only the ``modifier`` branch can satisfy that today. `explain.py` resolves
    a hydro / indicated-hydrogen locant against the parent skeleton's OWN
    atoms (``parent_index_by_locant``) and passes that atom's element, so
    caffeine's ``1H`` correctly reads "the N1 atom".

    The other two branches deliberately name no atom, because their callers
    cannot know one:

    * A ``suffix`` child was handed the element of the atom the suffix OWNS
      (caffeine's carbonyl OXYGEN), while the sentence is about the parent
      position the group hangs off (C2). Different atoms -- the old text
      asserted "the group hangs off O2" when it hangs off C2.
    * A ``substituent`` child was handed the element of the substituent's own
      first atom, while its locant is a position in whatever the substituent
      attaches TO. Verified live: caffeine's methyl at locant 1 rendered
      "the C1 atom" when position 1 is ring N1, and tryptophan's amino at
      locant 2 rendered "the N2 atom" when that parent has no N2 at all.

    Resolving a substituent's locant against the parent skeleton would not
    fix it either -- it is not reliably the parent's numbering. Verified on
    the golden corpus: DDT's ``4-chloro`` sits on a phenyl ring while the
    root is ethane, whose numbering has no position 4; and ibuprofen's
    ``2-methyl`` is position 2 of the propyl chain, which would silently
    resolve against the propanoic parent's unrelated C2. So these branches
    state only the position, which IS known, and let the hover highlight show
    which atoms are meant. Saying less is allowed; saying something false is
    not.
    """
    if kind == "modifier":
        if element:
            return f"Position {locant} — the {element}{locant} atom carries a hydrogen here."
        return f"Position {locant} — a hydrogen is fixed here."
    if kind == "suffix":
        return (
            f"Position {locant} — this group is attached at position {locant} "
            f"of the parent skeleton."
        )
    if kind == "substituent":
        return f"Position {locant} — this group is attached at position {locant}."
    if kind == "unmapped":
        return (
            f"Position {locant} — this part of the name refers to position "
            f"{locant}, but Orthonym could not work out which atom that is "
            f"here. The other parts are unaffected."
        )
    return f"Position {locant}."


def describe_multiplier(text: str) -> str | None:
    return _lookup(_MULTIPLIERS, text)
