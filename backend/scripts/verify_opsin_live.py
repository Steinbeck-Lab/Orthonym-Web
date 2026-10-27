"""Prove OPSIN actually works, at build time.

`orthonym --fetch-jars` proves the jars are there. It does not prove the JVM starts
or that the Orthonym engine's SELF-01 gate is running -- and without SELF-01 the gate
fails OPEN, so a name that should have downgraded to "fallback" ships as a
verified "pin". A slimmed image that dropped default-jre-headless would
build and pass a smoke test while quietly mislabelling every tier.

So: name the molecule README.md nominates for this check and assert the
verdict. A non-zero exit fails the Docker build, which is the point.

It also proves the OPSIN is the one ORTHONYM_OPSIN asks for: a main build is
accepted by the engine under this user (its private jar cache checks out),
its sidecar records a passing self-test, and the JVM really loaded it.
"""

import json
import os
import sys
from pathlib import Path

# A polycyclic cage, the Home "fallback" example. With a working OPSIN round
# trip the engine ships a verified systematic name: "fallback". Without the
# round trip the status can only be best_effort (measured 2026-10-09, engine
# 1.0.6), so anything but "fallback" means the gate did not run.
POLYCYCLIC_CAGE = "C1C2C3C4C1C5C2C(C3C4CC5=O)O"


def check_opsin() -> str | None:
    """None when the loaded OPSIN is the configured one, else what is wrong."""
    from orthonym.jars import active_opsin
    from orthonym.opsin_build import parse_choice

    from app.opsin_trace import running_opsin_version

    ref = parse_choice(os.environ.get("ORTHONYM_OPSIN"))
    found = active_opsin(download=False)
    loaded = running_opsin_version()  # NameToStructure.getVersion() in the JVM
    if ref is None:
        if found["label"] != "2.9.0" or loaded != "2.9.0":
            return f"expected OPSIN 2.9.0, resolved {found}, JVM loaded {loaded!r}"
        print("OK: OPSIN 2.9.0")
        return None
    if found["commit"] != ref:
        return f"expected OPSIN main {ref}, resolved {found}"
    sidecar = json.loads(Path(found["path"]).with_suffix(".json").read_text())
    if sidecar.get("selftest") != "pass":
        return f"OPSIN build sidecar has no passing self-test: {sidecar}"
    if not (loaded or "").endswith("+" + ref[:12]):
        return f"the JVM loaded OPSIN {loaded!r}, not the build of {ref[:12]}"
    print(f"OK: OPSIN {loaded} (jar sha256 {sidecar['jar_sha256']})")
    return None


def main() -> int:
    from app.orthonym_service import translate_one

    wrong = check_opsin()
    if wrong:
        print(f"FAIL: {wrong}", file=sys.stderr)
        return 1

    from app.main import EXAMPLES

    # Check EVERY advertised example, not just the polycyclic cage (audit
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
                "must be replaced (it has happened three times), or the engine is "
                "broken.",
                file=sys.stderr,
            )
            return 1

    result = translate_one(POLYCYCLIC_CAGE, best_effort=True)
    if result.status != "fallback":
        print(
            f"FAIL: expected 'fallback' for the polycyclic cage, got "
            f"{result.status!r}.\n"
            "The Orthonym engine's SELF-01 gate is not working. The usual cause is a "
            "missing JRE or missing jars -- check that "
            "default-jre-headless is installed and that "
            "`orthonym --fetch-jars` ran.",
            file=sys.stderr,
        )
        return 1
    print(f"OK: SELF-01 is live (polycyclic cage -> {result.status})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
