"""Plain-language descriptions of name parts, composed deterministically.

Two rules, both load-bearing:
  1. Text is looked up, never generated. Same input, same output, forever.
  2. A part with no glossary entry gets a NEUTRAL FACTUAL line stating what
     it is called and how many atoms it covers -- never invented chemistry.
     Being uninformative is acceptable; being confidently wrong is not.
"""

from __future__ import annotations

import re

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
    "onitrile": "a -C≡N triple bond",
    "carbonitrile": "a -C≡N triple bond",
    "carboxamide": "a -C(=O)N- group",
    "ophenone": "a C=O group (a carbonyl)",
    # Exact keys only (a counting word in front is stripped): the ending
    # "ic acid" inside "sulfonic acid" is not a carboxylic acid.
    "oic acid": "a -C(=O)OH group",
    "carboxylic acid": "a -C(=O)OH group",
    "ic acid": "a -C(=O)OH group",
    "oate": "an ester -C(=O)O- linkage",
    "ate": "an ester -C(=O)O- linkage",
    "carboxylate": "an ester -C(=O)O- linkage",
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

# "2-methylpropyl", "tert-butyl", "isopropyl": the text in front of a table key
# is only branching, so the key still names the chain. Anything else in front
# ("cyclo", "phen", "thio", "sulfon") changes what the ending means.
_BRANCHING = re.compile(r"^(?:[\d,']+-|tert-|sec-|iso|neo|n-|methyl|ethyl|propyl|butyl|-)*$")
_COUNTING = re.compile(r"^(?:di|tri|tetra|penta|hexa|hepta|octa|bis|tris|tetrakis)")


def _lookup(table: dict, text: str, *, endings: bool = False) -> str | None:
    """Exact key, or a key with only branching written in front of it
    (substituents), or a counted key ("dione" -> "one"). Never a key that
    merely ends the text: "thiol" is not "ol", "sulfonic acid" is not
    "ic acid", "phenoxy" is not "oxy". Unsure means None, and the caller
    then says only what it can count."""
    key = text.strip("-").lower()
    if key in table:
        return table[key]
    counted = _COUNTING.sub("", key, count=1) if not endings else key
    if not endings and counted != key and counted in table:
        return table[counted]
    if endings:
        for name, description in table.items():
            if key.endswith(name) and _BRANCHING.match(key[: -len(name)]):
                return description
    return None


def _parent_known(label: str) -> str | None:
    """Written parent labels ("purine", "ethan") against the stem table."""
    key = label.lower().rstrip("e")
    for candidate in (key, re.sub(r"(an|en|yn)$", "", key)):
        if candidate in _PARENTS:
            return _PARENTS[candidate]
    return None


def describe_part(kind: str, text: str, locant: str | None, atom_count: int,
                  copies: int = 1) -> str:
    label = text.strip("-")
    where = f" It sits at position {locant}." if locant else ""
    many = f" The name writes it once for {copies} copies." if copies > 1 else ""

    if kind == "substituent":
        known = _lookup(_SUBSTITUENTS, label, endings=True)
        if known:
            return f'"{label}" is {known}.{where}{many}'
    elif kind == "suffix":
        known = _lookup(_SUFFIXES, label)
        if known:
            return f'The "{label}" ending means {known}.{where}'
    elif kind == "parent":
        known = _parent_known(label)
        if known:
            return (
                f'"{label}" is {known}. It is the core the rest of the name '
                f"is built around, and it holds {atom_count} atoms.{many}"
            )
        return (
            f'"{label}" is the core skeleton the rest of the name is built '
            f"around. It has {atom_count} atoms.{many}"
        )
    elif kind == "modifier":
        return (
            f'"{label}" does not add atoms. It records where hydrogens sit, '
            f"which fixes where the double bonds go."
        )

    plural = "atom" if atom_count == 1 else "atoms"
    return f'"{label}" covers {atom_count} {plural} of this structure.{where}{many}'


def describe_locant(kind: str, locant: str, element: str | None = None, *, anomer: bool = False) -> str:
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
    if anomer and locant.lower() in ("alpha", "beta"):
        # Only a sugar's alpha/beta names an anomer. A Greek locant elsewhere
        # ("alpha,alpha,alpha-trifluorotoluene") is just a position.
        return (
            f'"{locant}" names the anomer: which way the OH on the ring carbon '
            f"next to the ring oxygen points."
        )
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


# One line per OPSIN parse-tree token kind (the element names app/opsin_trace
# records -- NOT the public tokenizer's categories this table used before
# Explain v2). A kind absent here gets no line from describe_token;
# explain_tree then uses GENERIC_TOKEN_LINE, which states only that the text
# is part of how the name is written.
_TOKEN_LINES = {
    "fusion": (
        'The letters in "{text}" say WHERE the two ring systems are fused '
        "together."
    ),
    "multiplier": (
        '"{text}" is a counting word — it says how many of the next group '
        "there are."
    ),
    "hydro": (
        '"{text}" records that hydrogens were added here, which fixes '
        "where the double bonds go."
    ),
    "indicatedHydrogen": (
        '"{text}" pins which ring atom carries a hydrogen. Without it the '
        "ring could be drawn more than one way."
    ),
    "stereoChemistry": (
        '"{text}" fixes the three-dimensional arrangement at the '
        "positions it names."
    ),
    "vonBaeyer": '"{text}" counts the atoms in each bridge of the ring cage.',
    "spiro": '"{text}" marks one atom shared between two rings.',
    "lambdaConvention": '"{text}" gives the bonding number of the atom it names, when that differs from its usual one.',
}

GENERIC_TOKEN_LINE = '"{text}" is part of how this name is written.'

# Ring-assembly multiplier words, OPSIN's own token table
# (`multipliers.xml`, tagname="ringAssemblyMultiplier") -- "bi" for two
# joined rings, up through "pentadeci" for fifteen. A hardcoded "two copies"
# for every one of these words would overclaim for anything past "bi":
# terphenyl's "ter" means three copies, not two. Verified live against the
# vendored jar that both "bi" (biphenyl) and "ter" (terphenyl) really tokenize
# to this one category.
_RING_ASSEMBLY_MULTIPLIER_COUNTS = {
    "bi": 2, "ter": 3, "quater": 4, "quinque": 5, "sexi": 6, "septi": 7,
    "octi": 8, "novi": 9, "deci": 10, "undeci": 11, "dodeci": 12,
    "trideci": 13, "tetradeci": 14, "pentadeci": 15,
}
_NUMBER_WORDS = {
    2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven",
    8: "eight", 9: "nine", 10: "ten", 11: "eleven", 12: "twelve",
    13: "thirteen", 14: "fourteen", 15: "fifteen",
}


def _ring_assembly_multiplier_line(text: str) -> str:
    count = _RING_ASSEMBLY_MULTIPLIER_COUNTS.get(text.strip("-").lower())
    word = _NUMBER_WORDS.get(count)
    if word:
        return (
            f'"{text}" means {word} copies of the ring that follows are '
            "joined together."
        )
    # Not reached against the current grammar -- every ring-assembly
    # multiplier word OPSIN defines is in the table above. Kept as a
    # truthful fallback (states WHAT the word does, not a guessed count)
    # rather than a wrong number if OPSIN ever adds one.
    return (
        f'"{text}" says how many copies of the ring that follows are '
        "joined together."
    )


def describe_token(category: str, text: str) -> str | None:
    """One line for a single raw name token, or None if the token teaches
    nothing. Elision vowels, hyphens and brackets fall in the second group.

    `None` means NO CHILD AT ALL, not a silent child: `explain.py`'s
    `_token_children` skips any token whose line is None, so no span is
    created for it either and its characters fall through to the owning
    segment. (An earlier draft of this docstring claimed such tokens "carry
    a span so the name stays continuous"; they do not.)
    """
    if category == "ringAssemblyMultiplier":
        return _ring_assembly_multiplier_line(text)
    template = _TOKEN_LINES.get(category)
    if template is None:
        return None
    return template.format(text=text)
