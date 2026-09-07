# -slim-bookworm, not -slim: the floating -slim tag follows Debian's current
# stable, so a rebuild after the trixie promotion swaps the whole userland
# under the JRE and font packages below without a line of this file changing.
# The Debian release is pinned; the patch level is not, so a rebuild still
# picks up security updates. Bump this deliberately, together with a run of
# the CDK and SELF-01 regression checks in README.md.
FROM python:3.12-slim-bookworm

# A JRE is required at runtime, not just build time: orthonym's SELF-01
# self-consistency gate needs a live JVM (via jpype) to actually round-trip
# candidate names through the vendored OPSIN/centres jars. Without it, SELF-01
# silently "fails open" and can ship a name that should have been suppressed
# and replaced with an honest fallback as if it were a verified PIN -- see
# backend/scripts/place_opsin_resources.py for the full story.
#
# libxrender1/libx11-6/libxext6/libsm6/libexpat1 are required at runtime by
# RDKit's rdkit.Chem.Draw module (used to render depiction_svg) even in
# headless Cairo mode -- confirmed the complete set via `ldd` on
# rdMolDraw2D's compiled .so in a clean python:3.12-slim container (missing
# any one of them crashes the whole app at import time in app/main.py with
# an ImportError naming that specific .so).
#
# fontconfig/libharfbuzz0b/libfreetype6/fonts-dejavu-core are required by CDK,
# which is now the DEFAULT depiction engine (app/cdk_bridge.py). CDK draws atom
# labels and CIP descriptors as real glyphs through java.awt, and
# default-jre-headless on slim ships libfontmanager.so WITHOUT its font stack.
# Measured in the built image, not guessed:
#
#   java.lang.UnsatisfiedLinkError: .../lib/libfontmanager.so:
#   libharfbuzz.so.0: cannot open shared object file
#
# Note how this failed: cdk_bridge.available() returned True and CIP labelling
# worked -- only the DRAW step died, and depiction.py caught it and quietly
# served RDKit pictures with no stereo labels. Nothing was broken enough to
# notice from the outside. cdk_bridge.self_check() is what caught it, which is
# the entire reason it asserts on a rendered SVG and not just on class loading.
# fonts-dejavu-core is not optional decoration: with fontconfig present but no
# font installed, AWT has nothing to measure and text metrics fail instead.
RUN apt-get update && apt-get install -y --no-install-recommends \
    default-jre-headless \
    libxrender1 \
    libx11-6 \
    libxext6 \
    libsm6 \
    libexpat1 \
    fontconfig \
    libfreetype6 \
    libharfbuzz0b \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /code

# CDK is FETCHED, not vendored, and it is the only one of the four vendored
# artifacts that can be: its release jar has a public URL. The other three --
# the Orthonym source, the OPSIN grammar resources and the opsin-cli and
# centres-cli jars -- are copied out of a private Orthonym checkout by
# scripts/vendor-orthonym.sh, so a clone has to run that first (see README).
#
# Pinned to an exact release AND checked against the SHA-256 recorded in
# vendor/cdk/NOTICE, which is tracked alongside this file. The check is the
# point: `cdk_bridge.py` resolves the newest cdk-*.jar in that directory and
# its CIP labelling depends on CDK internals rather than a public API, so a
# silently different jar is exactly the failure `cdk_bridge.self_check()`
# exists to catch -- better to fail here, loudly, at build time.
#
# --no-install-recommends on curl for the same reason as the block above:
# nothing else in the image needs it, and it is removed in the same layer so
# it never reaches the runtime image.
ARG CDK_VERSION=2.12
ARG CDK_SHA256=443d86e549edd659807a444770819a05f9ea626511f433ed99342c7568272e5a
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && mkdir -p vendor/cdk \
    && curl -fsSL -o "vendor/cdk/cdk-${CDK_VERSION}.jar" \
       "https://github.com/cdk/cdk/releases/download/cdk-${CDK_VERSION}/cdk-${CDK_VERSION}.jar" \
    && echo "${CDK_SHA256}  vendor/cdk/cdk-${CDK_VERSION}.jar" | sha256sum -c - \
    && apt-get purge -y --auto-remove curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
COPY vendor/ ./vendor/
RUN pip install --no-cache-dir -r requirements.txt

COPY scripts/place_opsin_resources.py ./scripts/place_opsin_resources.py
RUN python scripts/place_opsin_resources.py

COPY config/ ./config/
COPY app/ ./app/

# place_opsin_resources.py above only PLACES the jars. This proves they
# work: Orthonym's SELF-01 gate fails OPEN without a live JVM, so an image
# that lost default-jre-headless would build fine and then mislabel every
# confidence tier. A fused polycyclic must come back "fallback", never
# "pin". Fail the build here rather than discover it in production.
COPY scripts/verify_opsin_live.py ./scripts/verify_opsin_live.py

# Non-root at runtime. Every step above needs root (apt, pip into system
# site-packages, and place_opsin_resources.py writing jars next to the
# installed orthonym); nothing below writes to disk at all -- the name
# cache, job store and rate-limit counters are all Redis.
#
# --create-home is load-bearing, not tidiness: fontconfig builds its cache
# under $HOME/.cache the first time CDK asks java.awt to measure a glyph.
# With no writable HOME it does not fail, it re-scans the font directories
# on every single depiction, which reads as "the site got slow" and never
# as a permissions bug.
#
# The SELF-01 verification below deliberately runs AFTER this switch, as the
# same user that will serve traffic: a JVM the build can start as root but
# the runtime user cannot is exactly the failure this gate exists to catch,
# and it fails OPEN (an unverified name shipped as a PIN), so it must be
# proved under the real runtime identity, not a more privileged one.
RUN useradd --create-home --uid 10001 orthonym \
    && chown -R orthonym:orthonym /code
USER orthonym

RUN PYTHONPATH=/code python scripts/verify_opsin_live.py

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
