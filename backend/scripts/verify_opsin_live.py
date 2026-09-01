"""Prove OPSIN actually works, at build time.

place_opsin_resources.py places the jars. It does not prove the JVM starts
or that OpenSTOUT's SELF-01 gate is running -- and without SELF-01 the gate
fails OPEN, so a name that should have downgraded to "fallback" ships as a
verified "pin". A slimmed image that dropped default-jre-headless would
build and pass a smoke test while quietly mislabelling every tier.

So: name the molecule README.md nominates for this check and assert the
verdict. A non-zero exit fails the Docker build, which is the point.
"""

import sys

# A fused polycyclic. OpenSTOUT can name it, but the name does not
# round-trip, so a working SELF-01 gate must report "fallback". "pin" here
# means the gate silently failed open.
FUSED_POLYCYCLIC = "C1CC2CCC1(CC2)C3CCC4(CCC5(CCCC5C4C3)C)C"


def main() -> int:
    from app.openstout_service import translate_one

    result = translate_one(FUSED_POLYCYCLIC, best_effort=True)
    if result.status != "fallback":
        print(
            f"FAIL: expected 'fallback' for the fused polycyclic, got "
            f"{result.status!r}.\n"
            "OpenSTOUT's SELF-01 gate is not working. The usual cause is a "
            "missing JRE or missing vendored jars -- check that "
            "default-jre-headless is installed and that "
            "scripts/place_opsin_resources.py ran.",
            file=sys.stderr,
        )
        return 1
    print(f"OK: SELF-01 is live (fused polycyclic -> {result.status})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
