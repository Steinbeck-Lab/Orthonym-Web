"""Does a claimed name describe a structure?

OPSIN reads the name; RDKit makes a standard InChIKey for both structures; the
keys are compared block by block. The answer is only ever about STRUCTURE:
OPSIN reading a name says nothing about whether it is the preferred IUPAC
name, so no verdict here says "correct".
"""

from typing import Literal, Optional

# The longest claimed name the single check and a check job accept.
MAX_CLAIMED_NAME_LENGTH = 2000

Verdict = Literal[
    "same", "protonation", "stereo", "stereo_protonation", "different", "unreadable", "uncomparable",
]

VERDICT_TEXT: dict[str, str] = {
    "same": "Same structure",
    "protonation": "Same skeleton; protonation differs",
    "stereo": "Same skeleton; stereo or isotopes differ",
    "stereo_protonation": "Same skeleton; stereo or isotopes and protonation differ",
    "different": "Different structure",
    "unreadable": "OPSIN cannot read this name",
    "uncomparable": "Could not compare",
}


def compare_keys(input_key: Optional[str], claimed_key: Optional[str]) -> Verdict:
    """Compare two InChIKeys: connectivity, then stereo/isotopes, then
    protonation. A missing key (no InChI could be made) cannot be compared."""
    if not input_key or not claimed_key:
        return "uncomparable"
    a, b = input_key.split("-"), claimed_key.split("-")
    if a == b:
        return "same"
    if a[:2] == b[:2]:
        return "protonation"
    if a[0] == b[0]:
        # Both later blocks differing must not hide the protonation half.
        return "stereo_protonation" if a[2] != b[2] else "stereo"
    return "different"


def opsin_warnings(name: str) -> list[dict]:
    """OPSIN's warnings for a name it parsed (APPEARS_AMBIGUOUS,
    STEREOCHEMISTRY_IGNORED). The engine's opsin_parse keeps only the SMILES,
    as the CLI does, so a name OPSIN read with a warning looked like a clean
    parse. Same NameToStructure and CLI config opsin_parse uses; raises rather
    than returning [] when the JVM is missing, because an empty list here
    claims OPSIN raised no warning.
    """
    from orthonym import jvm_bridge

    # ponytail: a second parse of the same name (a few ms); fold into one
    # call if the engine ever exposes the OpsinResult itself.
    if not jvm_bridge._ensure_jvm():
        raise RuntimeError("OPSIN warnings need the in-process JVM")
    with jvm_bridge._LOCK:
        jvm_bridge._attach_thread()
        result = jvm_bridge._n2s().parseChemicalName(name, jvm_bridge._cfg(False))
        return [
            {"type": str(w.getType()), "message": str(w.getMessage())}
            for w in result.getWarnings()
        ]


def one_line(name: str) -> bool:
    """A name OPSIN can be asked about in-process. With a line break or other
    control character the engine's opsin_parse falls back to a `java -jar`
    subprocess that reads only the LAST line: a false verdict, at about 70x
    the cost."""
    return not any(ord(ch) < 32 or ord(ch) == 127 for ch in name)


def check_pair(smiles: str, name: str) -> dict:
    """The verdict for `name` against `smiles`, with what it rests on.

    Needs the in-process JVM (OPSIN), so it runs in a worker.
    """
    from orthonym.validation.opsin_roundtrip import opsin_parse
    from rdkit import Chem

    from app.orthonym_service import inchikey

    # The gate before OPSIN, for every caller: a name with a line break would
    # go to a subprocess that reads only its last line (see one_line), and the
    # length is the single check's own cap. Refused, not answered: no verdict
    # may say OPSIN cannot read a name OPSIN was never asked about.
    if not one_line(name) or len(name) > MAX_CLAIMED_NAME_LENGTH:
        raise ValueError("A claimed name must be one line of at most 2000 characters")

    input_mol = Chem.MolFromSmiles(smiles)
    raw = opsin_parse(name)
    claimed_mol = Chem.MolFromSmiles(raw) if raw else None
    input_key = inchikey(input_mol) if input_mol is not None else None
    if claimed_mol is None:
        verdict, claimed_key = "unreadable", None
    else:
        claimed_key = inchikey(claimed_mol)
        verdict = compare_keys(input_key, claimed_key)
    return {
        "verdict": verdict,
        "verdict_text": VERDICT_TEXT[verdict],
        "claimed_smiles": raw if claimed_mol is not None else None,
        "input_inchikey": input_key,
        "claimed_inchikey": claimed_key,
        "warnings": opsin_warnings(name) if claimed_mol is not None else [],
    }
