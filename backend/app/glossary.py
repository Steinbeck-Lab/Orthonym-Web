"""Plain-language descriptions of name parts, composed deterministically.

Two rules, both load-bearing:
  1. Text is looked up, never generated. Same input, same output, forever.
  2. A part with no glossary entry gets a NEUTRAL FACTUAL line stating what
     it is called and how many atoms it covers -- never invented chemistry.
     Being uninformative is acceptable; being confidently wrong is not.
"""

from __future__ import annotations

import re

from rdkit import Chem

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
    "oate": "a -C(=O)O- group (an ester linkage or a carboxylate salt)",
    "ate": "a -C(=O)O- group (an ester linkage or a carboxylate salt)",
    "carboxylate": "a -C(=O)O- group (an ester linkage or a carboxylate salt)",
}

# What a suffix line asserts about the atoms the suffix owns, by table key. A line is
# used only when the owned atoms bear it out (``suffix_claim_holds``); otherwise the
# neutral count line is: "benzoic acid methyl ester" and "benzoic acid hydrazide" end in
# "ic acid" but hold no -C(=O)OH, and cyclohexanone oxime's "one" holds no C=O.
_SUFFIX_CLAIMS = {
    "one": "carbonyl", "ophenone": "carbonyl",
    "oic acid": "acid", "carboxylic acid": "acid", "ic acid": "acid",
    "oate": "carboxylate", "ate": "carboxylate", "carboxylate": "carboxylate",
}

# Parent skeleton stems, as OPSIN's <group> token spells them. Verified live
# against the pinned jar -- these are the exact values the parent label
# derivation in explain_tree.py produces, not guesses at spelling.
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

# How many atoms a parent node may hold for the prose above to be true of it (per copy).
# A ring stem names a ring: a parent holding more ("benz" in benzophenone holds both
# rings) or fewer is not that ring. A chain stem counts the carbons the NAME writes, and
# a principal group may take one or two of them ("propan|oic acid" keeps two).
_PARENT_ATOMS = {
    "purin": (9, 9), "benzen": (6, 6), "benz": (6, 6), "indol": (9, 9), "pyridin": (6, 6),
    "naphthalen": (10, 10), "meth": (1, 1), "eth": (1, 2), "prop": (1, 3), "but": (2, 4),
    "pent": (3, 5), "hex": (4, 6), "hept": (5, 7), "oct": (6, 8), "acet": (1, 2),
}

# Retained parents that are not a "skeleton" at all.
_SPECIAL_PARENTS = {
    "hydrate": "water of crystallisation: water molecules that come with the compound",
}

# "2-methylpropyl", "tert-butyl", "isopropyl": the text in front of a table key
# is only branching, so the key still names the chain. Anything else in front
# ("cyclo", "phen", "thio", "sulfon") changes what the ending means.
_BRANCHING = re.compile(r"^(?:[\d,']+-|tert-|sec-|iso|neo|n-|methyl|ethyl|propyl|butyl|-)*$")
_COUNTING = re.compile(r"^(?:di|tri|tetra|penta|hexa|hepta|octa|bis|tris|tetrakis)")


def _lookup_key(table: dict, text: str, *, endings: bool = False) -> str | None:
    """The table key `text` stands for: the exact key, or a key with only branching
    written in front of it (substituents), or a counted key ("dione" -> "one"). Never
    a key that merely ends the text: "thiol" is not "ol", "sulfonic acid" is not
    "ic acid", "phenoxy" is not "oxy". Unsure means None, and the caller then says
    only what it can count."""
    key = text.strip("-").lower()
    if key in table:
        return key
    counted = _COUNTING.sub("", key, count=1) if not endings else key
    if not endings and counted != key and counted in table:
        return counted
    if endings:
        for name in table:
            if key.endswith(name) and _BRANCHING.match(key[: -len(name)]):
                return name
    return None


def _lookup(table: dict, text: str, *, endings: bool = False) -> str | None:
    key = _lookup_key(table, text, endings=endings)
    return None if key is None else table[key]


def suffix_claim(label: str) -> str | None:
    """The kind of claim the suffix line for `label` makes about its atoms
    ("carbonyl", "acid", "carboxylate"), or None when it makes none."""
    key = _lookup_key(_SUFFIXES, label)
    return None if key is None else _SUFFIX_CLAIMS.get(key)


def suffix_claim_holds(label: str, mol, atoms) -> bool:
    """True when the atoms a suffix owns bear out what its table line says. With no
    claim to check, True. With a claim and no molecule to check it on, False (the
    neutral line is always safe)."""
    claim = suffix_claim(label)
    if claim is None:
        return True
    if mol is None:
        return False
    owned = set(atoms)
    for o in owned:
        if o >= mol.GetNumAtoms():
            return False
        oxygen = mol.GetAtomWithIdx(o)
        if oxygen.GetSymbol() != "O":
            continue
        for bond in oxygen.GetBonds():
            carbon = bond.GetOtherAtom(oxygen)
            if carbon.GetSymbol() != "C" or bond.GetBondType() != Chem.BondType.DOUBLE:
                continue
            if claim == "carbonyl":
                return True
            for other in carbon.GetNeighbors():
                if other.GetIdx() == o or other.GetIdx() not in owned or other.GetSymbol() != "O":
                    continue
                if mol.GetBondBetweenAtoms(carbon.GetIdx(), other.GetIdx()).GetBondType() != Chem.BondType.SINGLE:
                    continue
                if claim == "carboxylate" or other.GetDegree() == 1:
                    return True
    return False


def _parent_key(label: str) -> str | None:
    key = label.lower().rstrip("e")
    for candidate in (key, re.sub(r"(an|en|yn)$", "", key)):
        if candidate in _PARENTS:
            return candidate
    return None


def _parent_known(label: str) -> str | None:
    """Written parent labels ("purine", "ethan") against the stem table."""
    key = _parent_key(label)
    return None if key is None else _PARENTS[key]


def parent_claim(label: str) -> tuple[str, tuple[int, int]] | None:
    """(the prose a parent line gives for `label`, the per-copy atom counts it is true
    of), or None when the label has no prose."""
    key = _parent_key(label)
    return None if key is None else (_PARENTS[key], _PARENT_ATOMS[key])


def _atoms(count: int) -> str:
    return f"{count} atom" if count == 1 else f"{count} atoms"


def describe_part(kind: str, text: str, locant: str | None, atom_count: int,
                  copies: int = 1, *, holds: bool = True) -> str:
    """One line for a part. `holds` is False when the caller found that the atoms the
    part owns do not bear out its table line (a suffix: ``suffix_claim_holds``); the
    neutral count line is then used."""
    label = text.strip("-")
    where = f" It sits at position {locant}." if locant else ""
    many = f" The name writes it once for {copies} copies." if copies > 1 else ""

    if kind == "substituent":
        known = _lookup(_SUBSTITUENTS, label, endings=True)
        if known:
            return f'"{label}" is {known}.{where}{many}'
    elif kind == "suffix":
        known = _lookup(_SUFFIXES, label)
        if known and holds:
            return f'The "{label}" ending means {known}.{where}'
    elif kind == "parent":
        special = _SPECIAL_PARENTS.get(label.lower())
        if special:
            return f'"{label}" is {special}.{many}'
        claim = parent_claim(label)
        per_copy = atom_count // copies if copies > 1 and atom_count % copies == 0 else atom_count
        if claim and claim[1][0] <= per_copy <= claim[1][1]:
            return (
                f'"{label}" is {claim[0]}. It is the core the rest of the name '
                f"is built around, and it holds {_atoms(atom_count)}.{many}"
            )
        return (
            f'"{label}" is the core skeleton the rest of the name is built '
            f"around. It has {_atoms(atom_count)}.{many}"
        )

    return f'"{label}" covers {_atoms(atom_count)} of this structure.{where}{many}'


# A functional-class word ("ketone" in "methyl ethyl ketone") owns the atoms the word
# adds. The line states what the word is only when the atoms it owns are exactly what
# that word adds; any other count gets the neutral line.
_FUNCTIONAL_WORDS = {
    "ketone": (2, "a C=O group (a carbonyl) joining the groups named before it"),
    "ether": (1, "an oxygen atom joining the groups named before it"),
    "sulfide": (1, "a sulfur atom joining the groups named before it"),
    "sulfoxide": (2, "an S=O group joining the groups named before it"),
    "sulfone": (3, "an S(=O)=O group joining the groups named before it"),
    "peroxide": (2, "an -O-O- link joining the groups named before it"),
    "anhydride": (1, "the oxygen atom that joins two acyl groups"),
    "alcohol": (1, "the oxygen of an -OH group on the group named before it"),
    "glycol": (2, "two -OH oxygens on the group named before it"),
    "oxime": (2, "an =N-OH group in place of the carbonyl oxygen"),
    "hydrazone": (2, "an =N-NH2 group in place of the carbonyl oxygen"),
    "semicarbazone": (5, "an =N-NH-C(=O)-NH2 group in place of the carbonyl oxygen"),
    "fluoride": (1, "a fluorine atom"),
    "chloride": (1, "a chlorine atom"),
    "bromide": (1, "a bromine atom"),
    "iodide": (1, "an iodine atom"),
}


def describe_functional(label: str, atom_count: int) -> str:
    word = label.strip("-").lower()
    if atom_count == 0:
        return (
            f'"{label}" is a word that says how the part named before it is joined or '
            f"changed. Orthonym counts no atoms of its own for it."
        )
    known = _FUNCTIONAL_WORDS.get(word)
    if known and known[0] == atom_count:
        return f'"{label}" is {known[1]}.'
    return f'"{label}" covers {_atoms(atom_count)} of this structure.'


def describe_locant(kind: str, locant: str, element: str | None = None, *, anomer: bool = False) -> str:
    """One line for a locant child, which is identified only by its locant.

    `element` names an atom in the sentence, so there is exactly one rule
    about it and it is not negotiable: **pass it only when the caller has
    resolved the real atom that carries this locant, in the numbering the
    locant is written in.** Anything else fabricates an atom label.

    Only the ``modifier`` branch can satisfy that today: explain_tree.py
    resolves a hydro / indicated-hydrogen locant against the parent
    skeleton's OWN atoms and passes that atom's element, so caffeine's ``1H``
    correctly reads "the N1 atom".

    The other branches deliberately name no atom, because their callers
    cannot know one:

    * A ``suffix`` child's locant is a position of the parent skeleton, while
      the atoms the suffix owns (caffeine's carbonyl OXYGEN) are different
      atoms. The old text asserted "the group hangs off O2" when it hangs off C2.
    * A ``substituent`` child's locant is a position in whatever the
      substituent attaches TO, not in the substituent's own numbering.
      Verified live: caffeine's methyl at locant 1 rendered "the C1 atom"
      when position 1 is ring N1, and tryptophan's amino at locant 2 rendered
      "the N2 atom" when that parent has no N2 at all.

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
    if kind == "oxy_number":
        # Only for a number written as "4-O-" whose atoms the caller proved: the
        # element is the one written next to the number.
        return (
            f"Position {locant} — this group is attached through the {element} atom "
            f"on position {locant} of the part named after it."
        )
    if kind == "oxy_element":
        return (
            f'"{locant}" names the element the group is joined through: the {locant} '
            f"atom of the part named after it, not a carbon."
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
    "fusedRingBridge": '"{text}" is a bridge across two positions of the ring system named after it.',
    "lambdaConvention": '"{text}" gives the bonding number of the atom it names, when that differs from its usual one.',
    "isotopeSpecification": '"{text}" is an isotope label: it says which isotope sits at the positions it names.',
    "oxidationNumberSpecifier": (
        'The Roman numeral in "{text}" is the oxidation number (charge state) of the '
        "metal written just before it."
    ),
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

    `None` means NO CHILD AT ALL, not a silent child: explain_tree.py then
    gives such a token the generic "is part of how this name is written" line
    when it must have a node, and no node otherwise.
    """
    if category == "ringAssemblyMultiplier":
        return _ring_assembly_multiplier_line(text)
    template = _TOKEN_LINES.get(category)
    if template is None:
        return None
    return template.format(text=text)


# "bi" in "bicyclo[2.2.2]octane" counts the RINGS of the cage; it is not a count of
# copies, which is what the line for a multiplier says.
_CAGE_RINGS = {"bi": 2, "tri": 3, "tetra": 4, "penta": 5, "hexa": 6, "hepta": 7, "octa": 8, "nona": 9, "deca": 10}


def describe_cage_multiplier(text: str) -> str:
    word = _NUMBER_WORDS.get(_CAGE_RINGS.get(text.strip("-").lower()))
    if word:
        return f'"{text}" counts the rings of the cage: {word} here.'
    return f'"{text}" counts the rings of the cage.'
