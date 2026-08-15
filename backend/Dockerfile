FROM python:3.12-slim

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
RUN apt-get update && apt-get install -y --no-install-recommends \
    default-jre-headless \
    libxrender1 \
    libx11-6 \
    libxext6 \
    libsm6 \
    libexpat1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /code

COPY requirements.txt .
COPY vendor/ ./vendor/
RUN pip install --no-cache-dir -r requirements.txt

COPY scripts/place_opsin_resources.py ./scripts/place_opsin_resources.py
RUN python scripts/place_opsin_resources.py

COPY app/ ./app/

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
