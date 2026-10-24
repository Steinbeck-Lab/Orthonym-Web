"""Does a claimed name describe a structure?

OPSIN reads the name; RDKit makes a standard InChIKey for both structures; the
keys are compared block by block. The answer is only ever about STRUCTURE:
OPSIN reading a name says nothing about whether it is the preferred IUPAC
name, so no verdict here says "correct".
"""

from typing import Literal, Optional

Verdict = Literal["same", "protonation", "stereo", "different", "unreadable", "uncomparable"]

VERDICT_TEXT: dict[str, str] = {
    "same": "Same structure",
    "protonation": "Same skeleton; protonation differs",
    "stereo": "Same skeleton; stereo or isotopes differ",
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
        return "stereo"
    return "different"
