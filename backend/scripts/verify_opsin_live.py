"""Prove OPSIN actually works, at build time.

`orthonym --fetch-jars` proves the jars are there. It does not prove the JVM starts
or that the Orthonym engine's SELF-01 gate is running -- and without SELF-01 the gate
fails OPEN, so a name that should have downgraded to "fallback" ships as a
verified "pin". A slimmed image that dropped default-jre-headless would
build and pass a smoke test while quietly mislabelling every tier.

So: name the molecule README.md nominates for this check and assert the
verdict. A non-zero exit fails the Docker build, which is the point.
"""

import sys

# A fused polycyclic. With a working OPSIN round trip the engine ships a
# verified systematic name: "fallback". Without OPSIN it abstains (measured
# 2026-09-28, engine 68f50d1), so anything but "fallback" means the gate did
# not run.
FUSED_POLYCYCLIC = "COC1C2=C(C)C(=O)OC2CC2CCC(O)C(C)C21C"


def main() -> int:
    from app.orthonym_service import translate_one

    from app.main import EXAMPLES

    # Check EVERY advertised example, not just the fused polycyclic (audit
    # item CC1-examples). These four are what Home renders as example chips,
    # each labelled with the tier it demonstrates, and until now this script
    # proved exactly one of them -- against its own private copy of the
    # SMILES rather than against the list the site actually serves, so the
    # two could drift apart silently.
    for example in EXAMPLES:
        got = translate_one(example["smiles"], best_effort=True)
        if got.status != example["expected_status"]:
            print(
                f"FAIL: Home advertises {example['label']!r} as "
                f"{example['expected_status']!r} but the engine returns "
                f"{got.status!r}. Either the engine changed and the example "
                "must be replaced (it has happened twice), or the engine is "
                "broken.",
                file=sys.stderr,
            )
            return 1

    result = translate_one(FUSED_POLYCYCLIC, best_effort=True)
    if result.status != "fallback":
        print(
            f"FAIL: expected 'fallback' for the fused polycyclic, got "
            f"{result.status!r}.\n"
            "The Orthonym engine's SELF-01 gate is not working. The usual cause is a "
            "missing JRE or missing jars -- check that "
            "default-jre-headless is installed and that "
            "`orthonym --fetch-jars` ran.",
            file=sys.stderr,
        )
        return 1
    print(f"OK: SELF-01 is live (fused polycyclic -> {result.status})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
