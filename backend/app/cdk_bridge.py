"""CDK (Chemistry Development Kit) inside OpenSTOUT's JVM, without touching its classpath.

WHY A CLASSLOADER AND NOT A CLASSPATH ENTRY
-------------------------------------------
OpenSTOUT's ``jvm_bridge`` owns the only ``startJVM`` call in the process. It boots with a
FIXED classpath -- the OPSIN jar and the centres jar, resolved from PROJECT_ROOT -- and it
records the pid that started the JVM, refusing to use one started by anybody else
(``vendor/openstout/src/openstout/jvm_bridge.py``, "fork-safe"). Three consequences, each
verified rather than assumed:

* We must not call ``startJVM`` ourselves. If we did, ``_start`` would see
  ``_STARTED_PID != pid`` and fall back to spawning ``java -jar`` per call --
  216 ms/call instead of 0.8 ms, for every name the site produces.
* A running JVM's classpath cannot be extended.
* ``jpype.startJVM(classpath=[...])`` OVERRIDES the ``CLASSPATH`` environment variable
  rather than merging it (``jpype/_core.py``: the default classpath is used only
  ``elif classpath is None``), so exporting ``CLASSPATH=/path/cdk.jar`` does nothing.

That leaves one route: load CDK in our own ``java.net.URLClassLoader`` and ask JPype for its
classes with ``JClass(name, loader=...)``.

WHY THE PARENT IS THE BOOTSTRAP LOADER, NOT THE SYSTEM LOADER
--------------------------------------------------------------
``centres-cli-1.2.1.jar`` is a fat jar that already carries **820 CDK classes** -- a partial
CDK with no ``org.openscience.cdk.depict`` package at all. Those classes are therefore
already on the system classpath. A URLClassLoader with the default (system) parent delegates
upward first, so half of CDK resolves to the old partial copy and half to ours. Measured, not
theorised::

    java.lang.IllegalAccessError: class org.openscience.cdk.layout.StructureDiagramGenerator
    tried to access method org.openscience.cdk.layout.AtomPlacer.prioritise(...)
    (StructureDiagramGenerator is in unnamed module of loader java.net.URLClassLoader;
     AtomPlacer is in unnamed module of loader 'app')

Passing ``null`` as the parent makes the bootstrap loader the parent, so ONLY ``java.*``
comes from above and every ``org.openscience.cdk.*`` name resolves inside our jar. The CDK
release jar is an uber-jar carrying its own dependencies, so nothing else is needed.

WHY THE CENTRES JAR IS IN OUR LOADER TOO, AND SECOND
-----------------------------------------------------
CIP labelling needs ``com.simolecule.centres.CdkLabeller`` to operate on the *same*
``IAtomContainer`` classes we parsed with -- a class from the system loader cannot touch one
from ours. So the centres jar is listed in this loader as well. URL order is load-bearing:
``URLClassLoader`` searches its URLs in order, so the full CDK jar is FIRST and wins every
``org.openscience.cdk`` name; the centres jar is second and contributes only
``com.simolecule.centres``. Reversing the two would resurrect the partial CDK.

This costs a second copy of those 859 classes in the JVM's metaspace. That is the price of
not modifying the vendored OpenSTOUT snapshot, which must stay byte-identical to upstream
(see CLAUDE.md) or the name cache's engine fingerprint changes and every cached name is
thrown away.

FAILURE MODEL
-------------
Every public function returns ``None``/``False`` rather than raising when CDK is unavailable.
CDK is an *enhancement*: a better picture and a second chance at a SMILES RDKit rejected.
A web process has no JVM at all (``jvm_guard``), so "no CDK" is a normal state, not an error.
"""

from __future__ import annotations

import logging
import os
import threading
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Re-entrant because the public entry points nest: depict_svg holds the lock and
# calls available(), which calls _loader(), and each of those takes it too. Not
# because of _annotate_cip -- that only reaches _cls, which takes no lock. Worth
# stating precisely: a reader who checked only _annotate_cip would conclude a
# plain Lock is safe here, and it is not.
_LOCK = threading.RLock()

# The loader, and the pid that built it. A JVM does not survive fork(), so neither
# does a classloader living inside it -- keyed by pid for exactly the reason
# jvm_bridge keys its own state that way.
_LOADER: Any = None
_LOADER_PID: Optional[int] = None
_CLASSES: dict[str, Any] = {}
# Configured DepictionGenerators, keyed (pid, width, height) -- see _generator.
_GENERATORS: dict[tuple, Any] = {}
_LOGGED_UNAVAILABLE = False

_CDK_PKG = "org.openscience.cdk"
_CENTRES_PKG = "com.simolecule.centres"

# No default picture size lives here. depiction.py owns the one the site uses,
# and a second copy of 240x180 would be a number to keep in step for nothing:
# the only production caller passes both explicitly. Hence width/height are
# REQUIRED below, and _SELF_CHECK_SIZE is the arbitrary size used by the checks
# that do not care what it is.
_SELF_CHECK_SIZE = (240, 180)

# ONE probe molecule for self_check(), which uses it twice -- once to prove CIP
# labelling still runs, once to prove drawing still runs. It was written out at
# both call sites; the docstring below promises "L-alanine must draw AND must
# come back labelled (S)", and that promise is only true while both sites name
# the SAME molecule. Two literals could drift into label-checking alanine and
# drawing something else, with nothing failing to say so.
#
# L-alanine: the smallest molecule with a defined tetrahedral centre, so a CIP
# pass that stopped labelling shows up as a missing (S).
_SELF_CHECK_SMILES = "C[C@H](N)C(=O)O"


def _log_unavailable_once(reason: str) -> None:
    global _LOGGED_UNAVAILABLE
    if not _LOGGED_UNAVAILABLE:
        _LOGGED_UNAVAILABLE = True
        logger.debug("CDK unavailable (%s); falling back to RDKit", reason)


@lru_cache(maxsize=1)
def _cdk_jar() -> Optional[str]:
    """The vendored CDK jar, or None.

    ``STITCH_CDK_JAR`` overrides it -- the escape hatch for pinning a different
    CDK build without rebuilding the image, and what the tests use to simulate
    a missing jar.
    """
    override = os.environ.get("STITCH_CDK_JAR")
    if override:
        return override if Path(override).exists() else None
    # backend/app/cdk_bridge.py -> backend/vendor/cdk/
    vendored = Path(__file__).resolve().parent.parent / "vendor" / "cdk"
    jars = sorted(vendored.glob("cdk-*.jar"))
    return str(jars[0]) if jars else None


@lru_cache(maxsize=1)
def _centres_jar() -> Optional[str]:
    """The centres jar OpenSTOUT already resolves, found the same way it does.

    Asking OpenSTOUT for it rather than globbing our own copy means CIP labels
    come from the same centres build the naming engine's stereo perception uses.
    A vendor refresh that bumps centres moves both together.
    """
    try:
        from openstout.perception.centres_bridge import _find_centres_jar

        return _find_centres_jar()
    except Exception:  # pragma: no cover - import guard
        return None


def _build_loader() -> Any:
    """Build the isolated loader. Caller holds _LOCK and has a live JVM."""
    import jpype

    cdk_jar = _cdk_jar()
    if not cdk_jar:
        _log_unavailable_once("no vendored cdk-*.jar found")
        return None

    URL = jpype.JClass("java.net.URL")
    # CDK first, centres second -- see the module docstring. The centres jar is
    # optional: without it we still depict, just with no CIP labels.
    urls = [URL("file:" + cdk_jar)]
    centres = _centres_jar()
    if centres:
        urls.append(URL("file:" + centres))

    # JObject(None, ClassLoader) is a typed Java null. A bare Python None would
    # be ambiguous between URLClassLoader's (URL[]) and (URL[], ClassLoader)
    # constructors; the typed null selects the second and makes the BOOTSTRAP
    # loader the parent, which is the whole point.
    bootstrap_parent = jpype.JObject(None, jpype.JClass("java.lang.ClassLoader"))
    return jpype.JClass("java.net.URLClassLoader")(urls, bootstrap_parent)


def _loader() -> Any:
    """The isolated CDK loader for THIS process, or None. Never raises."""
    global _LOADER, _LOADER_PID

    pid = os.getpid()
    with _LOCK:
        if _LOADER is not None and _LOADER_PID == pid:
            return _LOADER
        # First call here, or the loader was inherited across a fork and now
        # points into a JVM that no longer exists.
        _LOADER = None
        _CLASSES.clear()
        _GENERATORS.clear()
        _LOADER_PID = pid

        try:
            from openstout import jvm_bridge

            if not jvm_bridge._ensure_jvm():
                _log_unavailable_once("OpenSTOUT reports no usable JVM")
                return None
            jvm_bridge._attach_thread()
        except Exception as exc:
            _log_unavailable_once(f"JVM check failed: {exc}")
            return None

        try:
            _LOADER = _build_loader()
        except Exception as exc:
            _log_unavailable_once(f"classloader construction failed: {exc}")
            _LOADER = None
        return _LOADER


def _cls(name: str) -> Any:
    """A CDK/centres class from the isolated loader. Caller holds _LOCK."""
    cached = _CLASSES.get(name)
    if cached is not None:
        return cached
    import jpype

    loaded = jpype.JClass(name, loader=_LOADER)
    _CLASSES[name] = loaded
    return loaded


def available() -> bool:
    """True if this process can use CDK right now. Never raises."""
    with _LOCK:
        if _loader() is None:
            return False
        try:
            _cls(_CDK_PKG + ".smiles.SmilesParser")
            return True
        except Exception as exc:
            _log_unavailable_once(f"CDK classes not loadable: {exc}")
            return False


def _parser() -> Any:
    """A SmilesParser. Caller holds _LOCK.

    Built fresh per call rather than cached: CDK's SmilesParser is not
    documented as thread-safe, and construction is cheap next to the parse.
    """
    scob = _cls(_CDK_PKG + ".silent.SilentChemObjectBuilder")
    return _cls(_CDK_PKG + ".smiles.SmilesParser")(scob.getInstance())


def parse_smiles(smiles: str) -> Any:
    """Parse a SMILES with CDK. Returns an IAtomContainer, or None.

    Used when RDKit has already refused the string. CDK is more permissive
    about valence and aromaticity models, so it recovers a real minority of
    inputs -- and returns None on the rest, same as RDKit.
    """
    if not smiles:
        return None
    with _LOCK:
        if not available():
            return None
        try:
            return _parser().parseSmiles(smiles)
        except Exception as exc:
            logger.debug("CDK could not parse %r: %s", smiles, exc)
            return None


def atom_count(mol: Any) -> int:
    """Atoms in a CDK container, or 0. The counterpart of Mol.GetNumAtoms().

    Used for the same DoS bound RDKit's count serves: 2D coordinate generation
    is superlinear and this endpoint runs synchronously in the web process.
    CDK counts explicit atoms only (implicit hydrogens are a property, not
    atoms), which is the same convention RDKit's GetNumAtoms() uses here.
    """
    if mol is None:
        return 0
    # No lock: one JNI call on a container the caller already owns, touching
    # none of this module's shared state.
    try:
        return int(mol.getAtomCount())
    except Exception:
        return 0


def normalise_smiles(smiles: str) -> Optional[str]:
    """Round a SMILES through CDK and hand back its canonical form, or None.

    This is the whole SMILES-parsing fallback in one call: a string RDKit
    rejected goes in, and either a re-written string RDKit may well accept
    comes out, or None. It deliberately does NOT check the result against
    RDKit -- the caller does that, because the caller is the one that knows
    what it wanted the Mol for.

    The write-out is inline rather than its own helper: reaching here means
    parse_smiles already returned a container, which it only does after
    available() succeeded, so a separate function's re-check of that could
    never fire.
    """
    mol = parse_smiles(smiles)
    if mol is None:
        return None
    with _LOCK:
        try:
            flavour = _cls(_CDK_PKG + ".smiles.SmiFlavor")
            generator = _cls(_CDK_PKG + ".smiles.SmilesGenerator")(
                flavour.Absolute | flavour.UseAromaticSymbols
            )
            return str(generator.create(mol))
        except Exception as exc:
            logger.debug("CDK could not write SMILES: %s", exc)
            return None


def _annotate_cip(mol: Any) -> None:
    """Stamp CIP descriptors onto atoms and bonds as CDK annotation labels.

    A transliteration of cheminformatics-microservice's ``get_cip_annotation``
    (Steinbeck-Lab, MIT), which is itself a port of CDK's own depiction demo.
    Undefined-but-real stereocentres get "(?)" so an unspecified centre reads
    as unspecified rather than as absent -- the same honesty rule the
    confidence tiers follow.

    Caller holds _LOCK and has already generated 2D coordinates.
    """
    standard_generator = _cls(_CDK_PKG + ".renderer.generators.standard.StandardGenerator")
    stereocenters_cls = _cls(_CDK_PKG + ".stereo.Stereocenters")
    ibond = _cls(_CDK_PKG + ".interfaces.IBond")
    cycles = _cls(_CDK_PKG + ".graph.Cycles")

    stereocenters = stereocenters_cls.of(mol)

    for atom in mol.atoms():
        index = atom.getIndex()
        if (
            stereocenters.isStereocenter(index)
            and stereocenters.elementType(index) == stereocenters_cls.Type.Tetracoordinate
        ):
            atom.setProperty(standard_generator.ANNOTATION_LABEL, "(?)")

    for bond in mol.bonds():
        if bond.getOrder() != ibond.Order.DOUBLE:
            continue
        begin = bond.getBegin().getIndex()
        end = bond.getEnd().getIndex()
        if (
            stereocenters.elementType(begin) == stereocenters_cls.Type.Tricoordinate
            and stereocenters.elementType(end) == stereocenters_cls.Type.Tricoordinate
            and stereocenters.isStereocenter(begin)
            and stereocenters.isStereocenter(end)
            # A double bond inside a small ring has no E/Z to report.
            and cycles.smallRingSize(bond, 7) == 0
        ):
            bond.setProperty(standard_generator.ANNOTATION_LABEL, "(?)")

    if not mol.stereoElements().iterator().hasNext():
        # Nothing is actually defined, so every "(?)" above stands and there is
        # nothing for the labeller to compute.
        return

    base_mol = _cls(_CENTRES_PKG + ".BaseMol")
    _cls(_CENTRES_PKG + ".CdkLabeller").label(mol)

    prefix = standard_generator.ITALIC_DISPLAY_PREFIX
    for holder in (mol.atoms(), mol.bonds()):
        for item in holder:
            label = item.getProperty(base_mol.CIP_LABEL_KEY)
            if label is not None:
                item.setProperty(standard_generator.ANNOTATION_LABEL, prefix + label.toString())


def _generator(width: int, height: int) -> Any:
    """The configured DepictionGenerator for this size. Caller holds _LOCK.

    Cached because CDK's generator is IMMUTABLE -- every ``with*`` returns a new
    instance -- so one configured object is safe to share. Measured: building it
    is eight JNI calls at 0.056 ms, against 0.29 ms for the draw it configures,
    so rebuilding it per picture was 16% of the render step.

    Keyed on the pid as well as the size, for the same reason ``_loader`` is: the
    object lives inside a JVM that does not survive fork().
    """
    import jpype

    key = (os.getpid(), width, height)
    cached = _GENERATORS.get(key)
    if cached is not None:
        return cached

    standard_generator = _cls(_CDK_PKG + ".renderer.generators.standard.StandardGenerator")
    color = jpype.JClass("java.awt.Color")
    built = (
        _cls(_CDK_PKG + ".depict.DepictionGenerator")()
        # Atoms keep CDK's conventional element colours -- red oxygen, blue
        # nitrogen. That is chemistry's own convention inside a structure
        # drawing, not this site's palette.
        .withAtomColors(_cls(_CDK_PKG + ".renderer.color.CDK2DAtomColors")())
        # The CIP descriptor is NOT an atom. CDK draws annotations in red by
        # default, and red in this design system means chrome: nav, links,
        # buttons, the focus ring. A red (S) beside a molecule reads as the site
        # making a claim in its accent colour, which is exactly what DESIGN.md
        # keeps crimson away from. Ink, like every other statement the site
        # makes about what it knows.
        .withAnnotationColor(color.BLACK)
        .withSize(width, height)
        .withParam(standard_generator.StrokeRatio.class_, 1.0)
        .withAnnotationScale(0.7)
        .withFillToFit()
        .withBackgroundColor(color.WHITE)
    )
    _GENERATORS[key] = built
    return built


def depict_svg(smiles: str, width: int, height: int) -> Optional[str]:
    """Render a SMILES as a CDK SVG string, with CIP labels. None on any failure.

    Returns raw SVG, not a data URI -- ``depiction.py`` owns the encoding, so
    the CDK and RDKit paths cannot disagree about it, and owns the size too, so
    width and height are required here rather than defaulted twice.
    """
    if not smiles:
        return None
    with _LOCK:
        if not available():
            return None
        try:
            mol = _parser().parseSmiles(smiles)
            if mol is None:
                return None

            _cls(_CDK_PKG + ".layout.StructureDiagramGenerator")().generateCoordinates(mol)

            try:
                _annotate_cip(mol)
            except Exception as exc:
                # A picture without stereo labels beats no picture. This is the
                # one place CDK is allowed to half-succeed -- and the only guard
                # the CIP pass needs: without the centres jar, _annotate_cip's
                # first _cls("com.simolecule.centres.BaseMol") raises and lands
                # right here, so a separate _centres_jar() pre-check bought
                # nothing but a second thing to keep true.
                logger.debug("CIP annotation failed for %r: %s", smiles, exc)

            return str(_generator(width, height).depict(mol).toSvgStr("px"))
        except Exception as exc:
            logger.debug("CDK depiction failed for %r: %s", smiles, exc)
            return None


def cip_labels(smiles: str) -> list[str]:
    """The CIP descriptors CDK would draw on this molecule, in atom-then-bond order.

    The labels are drawn as glyph paths in the SVG, so they cannot be found by
    searching the rendered output. This reads them off the annotated molecule
    instead, which is what makes the CIP half of the pipeline testable at all.
    Returns [] when CDK is unavailable, exactly as it does for a molecule with
    no stereochemistry -- callers here only ever use it as a self-check, and
    ``available()`` answers the other question.
    """
    with _LOCK:
        if not available():
            return []
        try:
            mol = _parser().parseSmiles(smiles)
            _cls(_CDK_PKG + ".layout.StructureDiagramGenerator")().generateCoordinates(mol)
            _annotate_cip(mol)
            standard_generator = _cls(
                _CDK_PKG + ".renderer.generators.standard.StandardGenerator"
            )
            key = standard_generator.ANNOTATION_LABEL
            prefix = str(standard_generator.ITALIC_DISPLAY_PREFIX)
            found = []
            for holder in (mol.atoms(), mol.bonds()):
                for item in holder:
                    label = item.getProperty(key)
                    if label is not None:
                        found.append(str(label).replace(prefix, ""))
            return found
        except Exception as exc:
            logger.debug("CIP label read failed for %r: %s", smiles, exc)
            return []


def self_check() -> bool:
    """Prove the whole CDK path works in this process, including CIP labelling.

    Called from the Celery child's JVM boot alongside
    ``opsin_decompose.self_check()``. The classloader trick depends on which jar
    shadows which package -- a CDK or centres version bump can silently break it
    -- so it is verified at boot rather than discovered when a user's picture
    comes back blank or unlabelled.

    Asserts on the ANSWER, not merely on the absence of an exception: L-alanine
    must draw AND must come back labelled (S). A CIP pass that quietly stopped
    labelling would still return a perfectly good SVG.
    """
    if not available():
        return False
    if "S" not in cip_labels(_SELF_CHECK_SMILES):
        logger.warning("CDK self-check: L-alanine did not label as (S); CIP path is broken")
        return False
    svg = depict_svg(_SELF_CHECK_SMILES, *_SELF_CHECK_SIZE)
    return bool(svg) and svg.lstrip().startswith("<")
