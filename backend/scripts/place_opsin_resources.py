"""Places vendored OPSIN/CIP artifacts where orthonym expects them.

Three separate modules in orthonym each compute an identical PROJECT_ROOT as
4 parents up from their OWN installed file location and expect real artifacts
to be sitting there as siblings of "src/" in a full Orthonym engine dev checkout:

  orthonym/validation/opsin_grammar.py     -> opsin/opsin-core/src/main/resources/...
  orthonym/validation/opsin_roundtrip.py   -> opsin-cli-2.9.0-jar-with-dependencies.jar
  orthonym/perception/centres_bridge.py    -> centres-cli-1.2.1.jar

None of these ship with the pip package (pyproject.toml's packages =
["src/orthonym"] never includes them), and NONE are optional in the way
their graceful-degradation code paths suggest: without the two jars (and a
JVM via jpype), the SELF-01 self-consistency gate silently "fails open" --
it can ship a name that should have been suppressed and replaced with an
honest fallback as if it were a verified PIN. Confirmed by direct A/B testing
against the Orthonym engine dev checkout during this web app's Docker work: the exact
same molecule that correctly abstained/fell-back with these artifacts present
instead returned an unverified, wrong "PIN" without them.

This script does NOT import orthonym at all -- importing orthonym.validation
itself triggers the very opsin_grammar failure this script exists to prevent
(its __init__.py does `from .opsin_grammar import ...` at module level).
Instead it locates the module file on disk via sysconfig, exactly where pip
just installed it, and applies the same "4 parents up" arithmetic orthonym's
own source uses. Run once after `pip install -r requirements.txt` (the
Dockerfile and local dev setup both call this).
"""

import shutil
import sys
import sysconfig
from pathlib import Path


def main() -> int:
    vendored = Path(__file__).resolve().parent.parent / "vendor" / "opsin-resources"
    if not vendored.exists():
        print(f"error: vendored resources not found at {vendored}", file=sys.stderr)
        print("run scripts/vendor-orthonym.sh first", file=sys.stderr)
        return 1

    purelib = Path(sysconfig.get_paths()["purelib"])
    # Any of the three PROJECT_ROOT-computing modules resolves to the same
    # directory (src/orthonym/<subpkg>/<file>.py, same depth for all three).
    module_file = purelib / "orthonym" / "validation" / "opsin_grammar.py"
    if not module_file.exists():
        print(f"error: {module_file} not found -- is orthonym installed?", file=sys.stderr)
        return 1

    project_root = module_file.resolve().parent.parent.parent.parent

    opsin_dir_target = project_root / "opsin"
    if opsin_dir_target.exists():
        shutil.rmtree(opsin_dir_target)
    shutil.copytree(vendored / "opsin", opsin_dir_target)
    print(f"placed OPSIN grammar resources at {opsin_dir_target}")

    placed_jars = 0
    for jar in vendored.glob("*.jar"):
        target = project_root / jar.name
        shutil.copy2(jar, target)
        print(f"placed {jar.name} at {target}")
        placed_jars += 1
    if placed_jars == 0:
        print(
            "warning: no jars found in vendor/opsin-resources -- "
            "SELF-01 round-trip verification will silently fail open",
            file=sys.stderr,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
