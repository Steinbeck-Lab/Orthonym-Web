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
            f'"{label}" is part of this name, but STITCH could not work out '
            f"which atoms it refers to. The other parts are unaffected."
        )

    plural = "atom" if atom_count == 1 else "atoms"
    return f'"{label}" covers {atom_count} {plural} of this structure.{where}'


def describe_locant(kind: str, locant: str, element: str) -> str:
    if kind == "modifier":
        return f"Position {locant} — the {element}{locant} atom carries a hydrogen here."
    if kind == "suffix":
        return f"Position {locant} — the group hangs off {element}{locant}."
    return f"Position {locant} — the {element}{locant} atom."


def describe_multiplier(text: str) -> str | None:
    return _lookup(_MULTIPLIERS, text)
