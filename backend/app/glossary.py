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
    "methyl": "a one-carbon group (CH3 on its own)",
    "ethyl": "a two-carbon group (CH3-CH2- on its own)",
    "propyl": "a three-carbon chain",
    "butyl": "a four-carbon chain",
    "phenyl": "a benzene ring attached by one of its carbons",
    "chloro": "a chlorine atom",
    "bromo": "a bromine atom",
    "fluoro": "a fluorine atom",
    "iodo": "an iodine atom",
    "nitro": "an -NO2 group",
    "amino": "a nitrogen group (-NH2 on its own)",
    "hydroxy": "an -OH group",
    "acetyloxy": "an acetyl group joined through an oxygen (-O-C(=O)-CH3 on its own)",
    "methoxy": "a one-carbon group joined through an oxygen (-O-CH3 on its own)",
    "ethoxy": "a two-carbon group joined through an oxygen (-O-CH2CH3 on its own)",
    "acetyl": "a two-carbon group with a C=O (CH3-C(=O)- on its own)",
    "indolyl": "an indole ring system attached by one of its carbons",
    "oxy": "an -O- linkage joining two parts of the name",
}

_SUFFIXES = {
    "one": "a C=O group (a carbonyl)",
    "ol": "an -OH group",
    "al": "a -CHO group",
    "amine": "a nitrogen group (-NH2 on its own)",
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
    "hydrochloride": "hydrochloric acid (HCl) that comes with the compound as a salt",
    "hydrobromide": "hydrobromic acid (HBr) that comes with the compound as a salt",
    "hydroiodide": "hydroiodic acid (HI) that comes with the compound as a salt",
    "hydrofluoride": "hydrofluoric acid (HF) that comes with the compound as a salt",
}
# "monohydrate", "pentahydrate", "sesquihydrate": the hydrate with its count written in the same word.
_MULTIPLIED_HYDRATE = re.compile(r"^(?:mono|di|tri|tetra|penta|hexa|hepta|octa|nona|deca|hemi|sesqui)hydrate$",
                                 re.IGNORECASE)


def not_a_core(label: str) -> bool:
    """These come with the compound; none of them is a core the rest of the name is built around."""
    low = label.lower()
    return low in _SPECIAL_PARENTS or bool(_MULTIPLIED_HYDRATE.match(low))

# "2-methylpropyl", "tert-butyl", "isopropyl": the text in front of a table key
# is only branching, so the key still names the chain. Anything else in front
# ("cyclo", "phen", "thio", "sulfon") changes what the ending means.
_BRANCHING = re.compile(r"^(?:[\d,']+-|tert-|sec-|iso|neo|n-|methyl|ethyl|propyl|butyl|-)*$")
_COUNTING = re.compile(r"^(?:di|tri|tetra|penta|hexa|hepta|octa|bis|tris|tetrakis)")


_CHAIN_LENGTH = {"propyl": 3, "butyl": 4}


def _longest_chain(mol, atoms) -> list[int]:
    """The longest run of bonded, non-ring carbons inside each connected piece of `atoms`
    (one number per piece)."""
    pool = {a for a in atoms if a < mol.GetNumAtoms() and mol.GetAtomWithIdx(a).GetSymbol() == "C"
            and not mol.GetAtomWithIdx(a).IsInRing()}

    def walk(a, seen):
        best = 1
        for n in mol.GetAtomWithIdx(a).GetNeighbors():
            if n.GetIdx() in pool and n.GetIdx() not in seen:
                best = max(best, 1 + walk(n.GetIdx(), seen | {n.GetIdx()}))
        return best

    out, left = [], set(pool)
    while left:
        start = next(iter(left))
        piece, todo = set(), [start]
        while todo:
            a = todo.pop()
            if a in piece:
                continue
            piece.add(a)
            todo += [n.GetIdx() for n in mol.GetAtomWithIdx(a).GetNeighbors() if n.GetIdx() in pool]
        left -= piece
        out.append(max(walk(a, {a}) for a in piece))
    return out


def _chain_holds(key: str, mol, atoms) -> bool:
    """A "three- / four-carbon chain" line is said only when the longest carbon chain of each
    copy is that long: tert-butyl and isobutyl hold four carbons but no chain of four. With no
    molecule to measure on, the old line stands."""
    want = _CHAIN_LENGTH.get(key)
    if want is None or mol is None:
        return True
    runs = _longest_chain(mol, atoms)
    return bool(runs) and all(r == want for r in runs)


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


def parent_claim(label: str) -> tuple[str, tuple[int, int]] | None:
    """(the prose a parent line gives for `label`, the per-copy atom counts it is true
    of), or None when the label has no prose."""
    key = _parent_key(label)
    return None if key is None else (_PARENTS[key], _PARENT_ATOMS[key])


def _atoms(count: int) -> str:
    return f"{count} atom" if count == 1 else f"{count} atoms"


# A parent stem whose prose names benzene rings ("naphthalene -- two fused benzene
# rings") is true of a node only when it holds that many aromatic six-carbon rings per
# copy: 1,2,3,4-tetrahydronaphthalene keeps one, naphthalene-1,4-dione's quinone ring
# is not one, and 1,5,6,7-tetrahydro-4H-indol-4-one has no benzene ring at all.
_PARENT_BENZENE_RINGS = {"benzen": 1, "benz": 1, "indol": 1, "naphthalen": 2}


def parent_claim_holds(label: str, mol, atoms, copies: int = 1) -> bool:
    """True when the atoms a parent owns bear out the ring its prose names (counts are
    checked in describe_part). With no ring claim, True; with one and no molecule to
    check it on, False (the neutral line is always safe)."""
    key = _parent_key(label)
    need = _PARENT_BENZENE_RINGS.get(key) if key else None
    if not need:
        return True
    if mol is None:
        return False
    owned = set(atoms)
    benzene = [ring for ring in mol.GetRingInfo().AtomRings()
               if len(ring) == 6 and set(ring) <= owned
               and all(mol.GetAtomWithIdx(a).GetSymbol() == "C" and mol.GetAtomWithIdx(a).GetIsAromatic()
                       for a in ring)]
    return len(benzene) >= need * max(copies, 1)


def _hydrogens(mol, atom: int) -> int:
    """Hydrogens on `atom`, an isotope written as its own atom ("(2H3)methyl") included."""
    return mol.GetAtomWithIdx(atom).GetTotalNumHs(includeNeighbors=True)


def _heavy_degree(atom) -> int:
    """Neighbours of an RDKit atom that are not hydrogens."""
    return sum(1 for n in atom.GetNeighbors() if n.GetAtomicNum() > 1)


def _plain_atom(atom) -> bool:
    """An RDKit atom with no radical and no charge."""
    return atom.GetNumRadicalElectrons() == 0 and atom.GetFormalCharge() == 0


# What a group's table line leaves to be counted on the real atoms. The table line names
# the bare group "on its own"; when the atoms in this molecule carry a different number
# of hydrogens ("hydroxymethyl": its carbon carries 2), the line says so, measured.
# key -> (noun, possessive, which owned atoms, hydrogens of each in ONE bare copy).
# "end carbon" is a carbon not bonded to the group's own oxygen: acetyl's CH3 end.
_GROUP_HYDROGENS = {
    "methyl": ("carbon", "its", "C", (3,)),
    "ethyl": ("carbon", "its", "C", (3, 2)),
    "methoxy": ("carbon", "its", "C", (3,)),
    "ethoxy": ("carbon", "its", "C", (3, 2)),
    "acetyl": ("end carbon", "its", "end C", (3,)),
    "acetyloxy": ("end carbon", "its", "end C", (3,)),
    "amino": ("nitrogen", "the", "N", (2,)),
}
_SUFFIX_HYDROGENS = {"amine": ("nitrogen", "the", "N", (2,))}


def _counted(n: int) -> str:
    return "no hydrogen" if n == 0 else "1 hydrogen" if n == 1 else f"{n} hydrogens"


def _hydrogen_clause(spec, mol, atoms, copies: int) -> str:
    """' Here its carbon carries 2 hydrogens; other groups take the rest.' -- or '' when
    the atoms carry what the bare group does, or there is nothing to count them on."""
    noun, whose, which, bare = spec
    if mol is None or any(a >= mol.GetNumAtoms() for a in atoms):
        return ""
    element = which.split()[-1]
    picked = [a for a in sorted(set(atoms)) if mol.GetAtomWithIdx(a).GetSymbol() == element]
    if which.startswith("end"):
        own = set(atoms)
        picked = [a for a in picked
                  if not any(n.GetSymbol() == "O" and n.GetIdx() in own for n in mol.GetAtomWithIdx(a).GetNeighbors())]
    counts = sorted((_hydrogens(mol, a) for a in picked), reverse=True)
    # One atom per bare group (methyl, amino, the amine ending): one count per atom found,
    # so "diamine" expects two; a two-carbon group expects its pair once per copy.
    expected = sorted(bare * (len(counts) if len(bare) == 1 else max(copies, 1)), reverse=True)
    if not counts or counts == expected:
        return ""
    if len(counts) == 1:
        text = f"Here {whose} {noun} carries {_counted(counts[0])}"
    elif len(set(counts)) == 1:
        text = f"Here each of {whose} {noun}s carries {_counted(counts[0])}"
    else:
        text = f"Here {whose} {noun}s carry {', '.join(map(str, counts[:-1]))} and {counts[-1]} hydrogens"
    # "the rest" is taken by other groups only when no atom has more than the bare
    # group's count and none is a radical or ion (a missing hydrogen is then a bond).
    plain = all(_plain_atom(mol.GetAtomWithIdx(a)) for a in picked)
    if element == "C" and plain and len(counts) == len(expected) and all(c <= e for c, e in zip(counts, expected)):
        text += "; other groups take the rest"
    return f" {text}."


def _cores(count: int) -> str:
    return _NUMBER_WORDS.get(count, str(count))


def describe_part(kind: str, text: str, atom_count: int, copies: int = 1, *, holds: bool = True,
                  mol=None, atoms=(), cores: int = 1) -> str:
    """One line for a part. `holds` is False when the caller found that the atoms the
    part owns do not bear out its table line (a suffix: ``suffix_claim_holds``; a
    parent: ``parent_claim_holds``); the neutral count line is then used. `mol` and
    `atoms` are the traced molecule and the part's own atoms: a group whose table line
    names its bare formula ("methyl", "amino", the "amine" ending) gets the hydrogens
    its atoms really carry, counted. `cores` is the number of parent nodes in the name:
    with more than one, no parent is "the core the rest of the name is built around"."""
    label = text.strip("-")
    many = f" The name writes it once for {copies} copies." if copies > 1 else ""

    if kind == "substituent":
        key = _lookup_key(_SUBSTITUENTS, label, endings=True)
        # A line that names a carbon count or a formula is used only for the exact group:
        # "methylethyl" ends in "ethyl" but has three carbons.
        if key in _GROUP_HYDROGENS and key != label.lower():
            key = None
        if key in _CHAIN_LENGTH and not _chain_holds(key, mol, atoms):
            key = None
        if key:
            clause = _hydrogen_clause(_GROUP_HYDROGENS[key], mol, atoms, copies) if key in _GROUP_HYDROGENS else ""
            return f'"{label}" is {_SUBSTITUENTS[key]}.{clause}{many}'
    elif kind == "suffix":
        key = _lookup_key(_SUFFIXES, label)
        if key and holds:
            clause = _hydrogen_clause(_SUFFIX_HYDROGENS[key], mol, atoms, 1) if key in _SUFFIX_HYDROGENS else ""
            return f'The "{label}" ending means {_SUFFIXES[key]}.{clause}'
    elif kind == "parent":
        special = _SPECIAL_PARENTS.get(label.lower()) or (
            _SPECIAL_PARENTS["hydrate"] if _MULTIPLIED_HYDRATE.match(label) else None)
        if special:
            return f'"{label}" is {special}.{many}'
        claim = parent_claim(label)
        per_copy = atom_count // copies if copies > 1 and atom_count % copies == 0 else atom_count
        if claim and claim[1][0] <= per_copy <= claim[1][1] and holds:
            role = ("It is the core the rest of the name is built around" if cores <= 1
                    else f"It is one of the {_cores(cores)} cores this name is built from")
            return f'"{label}" is {claim[0]}. {role}, and it holds {_atoms(atom_count)}.{many}'
        if cores > 1:
            return f'"{label}" is one of the {_cores(cores)} cores this name is built from. It has {_atoms(atom_count)}.{many}'
        return (
            f'"{label}" is the core skeleton the rest of the name is built '
            f"around. It has {_atoms(atom_count)}.{many}"
        )

    return f'"{label}" covers {_atoms(atom_count)} of this structure.{many}'


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


def _hydrogen_taken(mol, atom: int) -> bool:
    """A named hydrogen the atom does not carry has given way to something the name
    writes elsewhere: a third heavy neighbour (a substituent, a spiro or fusion bond, an
    attachment) or a double / triple bond (an "=O", an "-ylidene")."""
    a = mol.GetAtomWithIdx(atom)
    if not _plain_atom(a):
        return False                  # an ylium / ide / radical ending removed the hydrogen itself
    multiple = any(b.GetBondType() in (Chem.BondType.DOUBLE, Chem.BondType.TRIPLE) for b in a.GetBonds())
    return _heavy_degree(a) >= 3 or multiple


def _modifier_line(locant: str, element: str | None, mol, atom: int | None) -> str:
    """A hydro / indicated / added hydrogen locant. The name puts a hydrogen on that atom
    (IUPAC P-31.2, P-14.7.1, P-14.7.2); whether the atom still carries one is measured."""
    if not element:
        return f"Position {locant} — the name puts a hydrogen at this position."
    if mol is None or atom is None or atom >= mol.GetNumAtoms():
        return f"Position {locant} — the name puts a hydrogen on the {element}{locant} atom."
    if _hydrogens(mol, atom) >= 1:
        return f"Position {locant} — the {element}{locant} atom carries a hydrogen here."
    if _hydrogen_taken(mol, atom):
        return (f"Position {locant} — the name puts a hydrogen on the {element}{locant} atom; "
                f"here a group or bond named elsewhere takes its place.")
    return f"Position {locant} — the name puts a hydrogen on the {element}{locant} atom; here that atom carries none."


def _anomeric_group(mol, atom: int | None) -> str | None:
    """What the anomeric carbon holds outside its ring, in words, when the bonds say:
    an OH (a free sugar), the O of a glycoside, or the one atom a C- or N-glycosyl
    group is joined through. None when it cannot be told."""
    if mol is None or atom is None or atom >= mol.GetNumAtoms():
        return None
    a = mol.GetAtomWithIdx(atom)
    outside = [n for n in a.GetNeighbors() if n.GetAtomicNum() > 1
               and not mol.GetBondBetweenAtoms(atom, n.GetIdx()).IsInRing()]
    oxygens = [n for n in outside if n.GetSymbol() == "O"]
    if len(oxygens) == 1:
        o = oxygens[0]
        heavy = _heavy_degree(o)
        if heavy == 1 and _hydrogens(mol, o.GetIdx()) >= 1:
            return "an OH"
        if heavy >= 2:
            return "the O that joins the sugar to the rest of the name"
        return None
    if not oxygens and len(outside) == 1:
        other = outside[0]
        if _heavy_degree(other) == 1:
            # a halogen, a thiol sulfur: it joins nothing, it is just there
            article = "an" if other.GetSymbol()[0] in "AEFHILMNORSX" else "a"
            return f"{article} {other.GetSymbol()} atom"
        return f"the {other.GetSymbol()} that joins the sugar to the rest of the name"
    return None


_RING_ELEMENTS = {"O": "oxygen", "S": "sulfur", "N": "nitrogen", "Se": "selenium"}


def _sugar_ring_element(mol, atom: int | None, pool) -> str | None:
    """The one element that closes the sugar's ring, when the bonds say: the ring atom
    next to the anomeric carbon `atom`, else the single hetero atom of the five- or
    six-membered rings inside `pool`. None when it is not one element."""
    if mol is None:
        return None
    if atom is not None and atom < mol.GetNumAtoms():
        a = mol.GetAtomWithIdx(atom)
        found = {n.GetSymbol() for n in a.GetNeighbors()
                 if n.GetAtomicNum() not in (1, 6) and mol.GetBondBetweenAtoms(atom, n.GetIdx()).IsInRing()}
        return next(iter(found)) if len(found) == 1 else None
    if pool is None:
        return None
    inside = set(pool)
    found = set()
    for ring in mol.GetRingInfo().AtomRings():
        if len(ring) in (5, 6) and set(ring) <= inside:
            hetero = [mol.GetAtomWithIdx(i).GetSymbol() for i in ring if mol.GetAtomWithIdx(i).GetAtomicNum() != 6]
            if len(hetero) == 1:
                found.add(hetero[0])
    return next(iter(found)) if len(found) == 1 else None


def describe_locant(kind: str, locant: str, element: str | None = None, *, anomer: bool = False,
                    mol=None, atom: int | None = None, pool=None) -> str:
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
        # ("alpha,alpha,alpha-trifluorotoluene") is just a position. 2-Carb-6.2: the
        # anomeric group is compared with the anomeric reference atom; a glycoside
        # holds an O-R there, not an OH (2-Carb-33.1), so what it holds is read off the
        # bonds of `atom`, the lit anomeric carbon.
        group = _anomeric_group(mol, atom)
        here = f" Here that group is {group}." if group else ""
        element = _sugar_ring_element(mol, atom, pool)
        ring = (f"the ring {_RING_ELEMENTS[element]}" if element in _RING_ELEMENTS else
                f"the ring {element} atom" if element else "the ring's heteroatom")
        return (
            f'"{locant}" names the anomer: which way the group on the ring carbon '
            f"next to {ring} points, relative to the sugar's reference stereocentre.{here}"
        )
    if kind == "modifier":
        return _modifier_line(locant, element, mol, atom)
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
    "vonBaeyer": '"{text}" counts the atoms in each bridge of the ring cage.',
    "fusedRingBridge": '"{text}" is a bridge across two positions of the ring system named after it.',
    "lambdaConvention": '"{text}" gives the bonding number of the atom it names, when that differs from its usual one.',
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


# Stereo marks, by what they say (IUPAC 2013 P-93, P-92.4, 2-Carb-4 and 2-Carb-8). Only a
# mark that carries a locant ("2S", "9Z", "17beta", "NE") fixes the arrangement "at the
# positions it names"; every other kind gets a line of its own.
_STEREO_LOCANT = r"(\d+[a-z]?'*|[A-Z][a-z]?'*)"
_LOCATED = re.compile(_STEREO_LOCANT + r"([RSrs]|[EZ]|alpha|beta)$")
_LOCATED_STARRED = re.compile(_STEREO_LOCANT + r"([RS])\*$")
_LOCATED_RACEMIC = re.compile(r"(\d+[a-z]?'*)(RS|SR)$")
_RACEMATE = frozenset({"rac", "RS", "SR", "+-", "±", "DL"})
_ROTATION = {"+": "to the right", "-": "to the left"}
_SUGAR_PREFIX = {
    "glycero": "glyceraldehyde", "erythro": "erythrose", "threo": "threose", "arabino": "arabinose",
    "lyxo": "lyxose", "ribo": "ribose", "xylo": "xylose", "allo": "allose", "altro": "altrose",
    "galacto": "galactose", "gluco": "glucose", "gulo": "gulose", "ido": "idose", "manno": "mannose",
    "talo": "talose",
}
_RELATIVE = ("only as a relative arrangement, not an absolute one; it does not say which of the two "
             "mirror-image forms is meant")


def describe_stereo(text: str, within: str | None = None) -> str:
    """The line for one stereo mark. `within` is "rel" or "rac" when the mark is written
    inside a "rel-(...)" / "rac-(...)" set, which changes what every mark in it says."""
    # "+-" and "-" are marks of their own; any other mark loses a trailing hyphen.
    mark = text if text in _RACEMATE or text in _ROTATION else text.strip("-")
    located = _LOCATED.match(mark)
    if mark in _RACEMATE:
        # P-93.1.3; P-103.1.3.1 and 2-Carb-4.4 for "DL"
        return f'"{mark}" marks a racemate: an equal mix of the two mirror-image forms.'
    racemic = _LOCATED_RACEMIC.match(mark)
    if racemic:
        first, second = racemic.group(2)
        return (f'"{mark}" marks a racemate: an equal mix of the two mirror-image forms, {first} at '
                f"position {racemic.group(1)} in one and {second} in the other.")
    if mark == "rel":
        # P-93.1.2.1
        return (f'"rel" says the marks of its set give only a relative arrangement; it does not say '
                f"which of the two mirror-image forms is meant.")
    if mark in _ROTATION:
        # 2-Carb-4.5: the sign of optical rotation, not a configuration
        return (f'"{mark}" gives the sign of optical rotation: this form turns polarised light '
                f"{_ROTATION[mark]}. It does not by itself say how the atoms are arranged.")
    starred = _LOCATED_STARRED.match(mark)
    if starred or (located and within == "rel" and mark[-1] in "RS"):
        return f'"{mark}" gives the arrangement at the position it names {_RELATIVE}.'
    if located and within == "rac":
        return (f'"{mark}" is part of a racemate mark (rac): the name means an equal mix of '
                f"this form and its mirror image.")
    if located:
        return f'"{mark}" fixes the three-dimensional arrangement at the positions it names.'
    if mark in ("D", "L"):
        # 2-Carb-4.2; P-103.1.3.1 (amino acids)
        return (f'"{mark}" is a Fischer label: it puts the part named after it in the {mark} series, '
                f"by comparing one of its stereocentres with {mark}-glyceraldehyde.")
    if mark in ("cis", "trans"):
        # P-93.5.1.2 (rings), P-93.4.2.1.1 (double bonds)
        side = "on the same side" if mark == "cis" else "on opposite sides"
        return f'"{mark}" says two groups lie {side} of the ring or double bond they are on.'
    if mark in ("R", "S") and within == "rel":
        return f'"{mark}" gives the arrangement at one stereocentre {_RELATIVE}.'
    if mark in ("R", "S") and within == "rac":
        return (f'"{mark}" is part of a racemate mark (rac): the name means an equal mix of '
                f"this form and its mirror image.")
    if mark in ("R", "S"):
        return (f'"{mark}" fixes the three-dimensional arrangement at one stereocentre; the mark '
                f"itself carries no position number.")
    if mark in ("R*", "S*"):
        return f'"{mark}" gives the arrangement at one stereocentre {_RELATIVE}.'
    if mark in ("E", "Z"):
        # P-92.4.1; P-93.4.2.1.3: no locant when the name needs none
        side = "on opposite sides" if mark == "E" else "on the same side"
        return (f'"{mark}" fixes the arrangement at one double bond: its higher-ranked groups lie {side}. '
                f"The mark itself carries no position number.")
    sugar = _SUGAR_PREFIX.get(mark.lower())
    if sugar and mark.lower() == "glycero":
        return f'"{mark}" is a sugar configuration prefix: the stereocentre it covers is arranged as in {sugar}.'
    if sugar:
        # 2-Carb-4.3, 2-Carb-8.4 (the centres it covers need not be next to each other)
        return f'"{mark}" is a sugar configuration prefix: the stereocentres it covers are arranged as in {sugar}.'
    return f'"{mark}" is a stereo descriptor: part of how the name gives the three-dimensional arrangement.'


def _spiro_line(text: str) -> str:
    """P-24.2.1: "spiro[4.5]" -- two rings share one atom, and the numbers count the other
    atoms of each ring. P-24.2.2: after "di", "tri" (a polyspiro system) the numbers count
    the atoms that link the shared atoms, in order along the system."""
    inside = re.fullmatch(r"spiro\[([^\]]*)\]", text.strip("-"))
    numbers = inside.group(1).split(".") if inside else []
    if len(numbers) == 2 and all(n.isdigit() for n in numbers):
        return (f'"{text}" names two rings that share one atom; {numbers[0]} and {numbers[1]} count '
                f"the other atoms in each ring.")
    if len(numbers) > 2 and "^" in text:
        # "4^8": the raised number is a position on the system, not a count of atoms
        return (f'"{text}" names rings joined at single shared atoms (the counting word before it says '
                f"how many); its plain numbers count the atoms between them, in order along the system, "
                f"and a raised number is a position, not a count.")
    if len(numbers) > 2:
        return (f'"{text}" names rings joined at single shared atoms (the counting word before it says '
                f"how many); its numbers count the atoms between them, in order along the system.")
    return f'"{text}" names rings that share single atoms.'


def _isotope_line(text: str) -> str:
    """P-82.2.1: a locant in front of the nuclide names the positions; with none, every
    position of the part that can carry it is meant (P-82.6.1.3)."""
    if "-" in text.strip("()-"):
        return f'"{text}" is an isotope label: it says which isotope sits at the positions it names.'
    return (f'"{text}" is an isotope label: it says which isotope the part named after it carries in '
            f"place of the usual one; the label gives no position number.")


def describe_token(category: str, text: str) -> str | None:
    """One line for a single raw name token, or None if the token teaches
    nothing. Elision vowels, hyphens and brackets fall in the second group.

    `None` means NO CHILD AT ALL, not a silent child: explain_tree.py then
    gives such a token the generic "is part of how this name is written" line
    when it must have a node, and no node otherwise.
    """
    if category == "ringAssemblyMultiplier":
        return _ring_assembly_multiplier_line(text)
    if category == "stereoChemistry":
        return describe_stereo(text)
    if category == "spiro":
        return _spiro_line(text)
    if category == "isotopeSpecification":
        return _isotope_line(text)
    template = _TOKEN_LINES.get(category)
    if template is None:
        return None
    return template.format(text=text)


def token_line(category: str, text: str) -> str:
    """describe_token's line, or the generic one for a kind the table does not cover."""
    return describe_token(category, text) or GENERIC_TOKEN_LINE.format(text=text)


# "bi" in "bicyclo[2.2.2]octane" counts the RINGS of the cage; it is not a count of
# copies, which is what the line for a multiplier says.
_CAGE_RINGS = {"bi": 2, "tri": 3, "tetra": 4, "penta": 5, "hexa": 6, "hepta": 7, "octa": 8, "nona": 9, "deca": 10}


def describe_cage_multiplier(text: str) -> str:
    word = _NUMBER_WORDS.get(_CAGE_RINGS.get(text.strip("-").lower()))
    if word:
        return f'"{text}" counts the rings of the cage: {word} here.'
    return f'"{text}" counts the rings of the cage.'
