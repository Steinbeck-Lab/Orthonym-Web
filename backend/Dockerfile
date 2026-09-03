FROM python:3.12-slim

# A JRE is required at runtime, not just build time: openstout's SELF-01
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

COPY requirements.txt .
COPY vendor/ ./vendor/
RUN pip install --no-cache-dir -r requirements.txt

COPY scripts/place_opsin_resources.py ./scripts/place_opsin_resources.py
RUN python scripts/place_opsin_resources.py

COPY config/ ./config/
COPY app/ ./app/

# place_opsin_resources.py above only PLACES the jars. This proves they
# work: OpenSTOUT's SELF-01 gate fails OPEN without a live JVM, so an image
# that lost default-jre-headless would build fine and then mislabel every
# confidence tier. A fused polycyclic must come back "fallback", never
# "pin". Fail the build here rather than discover it in production.
COPY scripts/verify_opsin_live.py ./scripts/verify_opsin_live.py
RUN PYTHONPATH=/code python scripts/verify_opsin_live.py

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
