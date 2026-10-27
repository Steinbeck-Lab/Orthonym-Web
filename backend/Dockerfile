# -slim-bookworm, not -slim: the floating -slim tag follows Debian's current
# stable, so a rebuild after the trixie promotion swaps the whole userland
# under the JRE and font packages below without a line of this file changing.
# The Debian release is pinned; the patch level is not, so a rebuild still
# picks up security updates. Bump this deliberately, together with a run of
# the CDK and SELF-01 regression checks in README.md.
FROM python:3.12-slim-bookworm

# A JRE is required at runtime, not just build time: the Orthonym engine's SELF-01
# self-consistency gate needs a live JVM (via jpype) to actually round-trip
# candidate names through the OPSIN/centres jars. Without it, SELF-01
# silently "fails open" and can ship a name that should have been suppressed
# and replaced with an honest fallback as if it were a verified PIN.
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

# CDK is FETCHED, not vendored: its release jar has a public URL.
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

# The Orthonym engine is installed from GitHub, not from a local copy, at the
# commit ORTHONYM_REF names. A BuildKit git source, not the `git+https` line
# in requirements.txt: BuildKit resolves the ref to a commit and keys this
# layer on it. The default is a pinned commit, so a rebuild gives the same
# image; CI and the engine-watch job still follow main through requirements.txt.
#
# The engine fetches its own OPSIN 2.9.0 and centres 1.2.1 jars from their
# official releases and checks each against a pinned SHA-256 (orthonym/jars.py).
# ORTHONYM_JAR_DIR puts them in one place outside any home directory, and
# `--fetch-jars` fails the build if either is missing -- the install-time
# prefetch alone is best effort. They are downloaded as root and written
# 0600, so they are made readable for the runtime user below.
#
# ORTHONYM_REF picks another commit (full 40-character SHA), branch or tag:
# `--build-arg ORTHONYM_REF=main` for the newest engine.
#
# --keep-git-dir is only there for .git/HEAD, which BuildKit leaves as the
# resolved commit SHA. A directory install records no commit for pip, so it
# is copied to ORTHONYM_COMMIT_FILE and /api/health reports it.
ARG ORTHONYM_REF=73de4d1576eb8481b29e73b767cbc9e13dbb574b
ADD --keep-git-dir=true https://github.com/Steinbeck-Lab/Orthonym.git#${ORTHONYM_REF} /tmp/orthonym
ENV ORTHONYM_JAR_DIR=/opt/orthonym/jars \
    ORTHONYM_COMMIT_FILE=/opt/orthonym/COMMIT
COPY requirements.txt .
COPY --from=ghcr.io/astral-sh/uv:0.11.8 /uv /usr/local/bin/uv
RUN grep -v '^orthonym @' requirements.txt > /tmp/requirements.txt \
    && uv pip install --system --no-cache /tmp/orthonym -r /tmp/requirements.txt \
    && mkdir -p /opt/orthonym && cp /tmp/orthonym/.git/HEAD "$ORTHONYM_COMMIT_FILE" \
    && rm -rf /tmp/orthonym /tmp/requirements.txt \
    && orthonym --fetch-jars \
    && chmod -R a+rX /opt/orthonym

# Non-root at runtime. The steps above need root (apt, pip into system
# site-packages); at run time nothing writes to disk at all -- the name
# cache, job store and rate-limit counters are all Redis.
#
# --create-home is load-bearing, not tidiness: fontconfig builds its cache
# under $HOME/.cache the first time CDK asks java.awt to measure a glyph.
# With no writable HOME it does not fail, it re-scans the font directories
# on every single depiction, which reads as "the site got slow" and never
# as a permissions bug.
#
# The SELF-01 verification below deliberately runs AFTER the USER switch, as the
# same user that will serve traffic: a JVM the build can start as root but
# the runtime user cannot is exactly the failure this gate exists to catch,
# and it fails OPEN (an unverified name shipped as a PIN), so it must be
# proved under the real runtime identity, not a more privileged one.
RUN useradd --create-home --uid 10001 orthonym

# The OPSIN every process of this image names and explains with. The web app
# uses a pinned commit of OPSIN's main branch, not the 2.9.0 release the
# Python package defaults to: it reads adduct names with an em dash before a
# locanted component (dan2097/opsin#344) and phane names. Never a bare `main`,
# which would follow the branch tip and change names with no rebuild here.
# `--build-arg ORTHONYM_OPSIN=2.9.0` is the rollback; the release jar is
# already in the image, so it needs no JDK and no build.
#
# Before COPY app/, so an app edit does not rebuild it. A main jar is
# compiled once, here (`orthonym --fetch-jars`, about 15 s): it
# needs javac, so a JDK is installed for this step and purged in the same
# layer (the JRE above stays). The engine accepts a built jar only from
# <jar dir>/opsin-main owned by the user that runs it, mode 0700, so that
# directory is made for uid 10001 and the build runs as that user. A jar
# built by root would be refused at run time.
#
# ORTHONYM_NO_DOWNLOAD=1: at run time nothing is fetched or built. A jar that
# is missing or fails its checks is an error, never a build per request.
ARG ORTHONYM_OPSIN=main@7bb0cbdc7db891518a83d59e06ca2a6349152ff7
ENV ORTHONYM_OPSIN=${ORTHONYM_OPSIN} \
    ORTHONYM_NO_DOWNLOAD=1
RUN case "$ORTHONYM_OPSIN" in \
       2.9.0) ;; \
       main@*) echo "$ORTHONYM_OPSIN" | grep -Eqx 'main@[0-9a-f]{40}' \
          && apt-get update && apt-get install -y --no-install-recommends default-jdk-headless \
          && install -d -o orthonym -g orthonym -m 0700 "$ORTHONYM_JAR_DIR/opsin-main" \
          && runuser -u orthonym -- orthonym --fetch-jars \
          && sha256sum "$ORTHONYM_JAR_DIR"/opsin-main/opsin-main-*.jar \
          && apt-get purge -y --auto-remove default-jdk-headless \
          && rm -rf /var/lib/apt/lists/* ;; \
       *) echo "ORTHONYM_OPSIN must be 2.9.0 or main@<40-hex commit>, not $ORTHONYM_OPSIN" >&2; exit 1 ;; \
       esac

COPY config/ ./config/
COPY app/ ./app/

# `--fetch-jars` above only proves the jars are there. This proves they
# work: the Orthonym engine's SELF-01 gate fails OPEN without a live JVM, so an image
# that lost default-jre-headless would build fine and then mislabel every
# confidence tier. A fused polycyclic must come back "fallback", never
# "pin". Fail the build here rather than discover it in production.
COPY scripts/verify_opsin_live.py ./scripts/verify_opsin_live.py

RUN chown -R orthonym:orthonym /code
USER orthonym

RUN PYTHONPATH=/code python scripts/verify_opsin_live.py

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
