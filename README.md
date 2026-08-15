# Orthonym

Verified IUPAC names for Chemical Structures — a public prototype putting [Orthonym](https://github.com/Kohulan/Orthonym)'s deterministic, rule-based naming engine in front of visitors. See `PRODUCT.md` for product context and `DESIGN.md` for the visual system ("Needlework Sampler").

## Run with Docker (recommended)

```bash
docker compose up -d --build
```

- Frontend: http://localhost:8080
- Backend: http://localhost:8000 (docs at `/docs`)

## Run locally without Docker

```bash
# backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/place_opsin_resources.py   # see "Orthonym dependency" below — required
uvicorn app.main:app --host 0.0.0.0 --port 8000

# frontend (separate terminal)
cd frontend
npm install
npm run dev   # proxies /api -> http://localhost:8000
```

## The Orthonym dependency

Orthonym isn't published on PyPI in the form Orthonym needs (`name_tiered()`, `general_fallback`), so `backend/requirements.txt` installs it from `backend/vendor/orthonym` — a snapshot vendored from the local sibling project, not a live path dependency. This keeps Docker builds self-contained (a container can't reach outside its build context) and makes the backend reproducible without assuming `/home/kohulan/Orthonym/Project` exists on the host it's built on.

**Refresh the snapshot** after pulling Orthonym changes you want Orthonym to pick up:

```bash
./scripts/vendor-orthonym.sh
```

### The part that isn't optional: SELF-01 needs a real JVM

Orthonym ships three modules that each compute an identical `PROJECT_ROOT` (4 parents up from their own installed file) and expect real artifacts sitting there as siblings of `src/` in a full dev checkout:

| Module | Expects |
|---|---|
| `validation/opsin_grammar.py` | `opsin/opsin-core/src/main/resources/...` |
| `validation/opsin_roundtrip.py` | `opsin-cli-2.9.0-jar-with-dependencies.jar` |
| `perception/centres_bridge.py` | `centres-cli-1.5.jar` |

None of these ship with the pip package. `scripts/vendor-orthonym.sh` vendors all three into `backend/vendor/opsin-resources/`, and `backend/scripts/place_opsin_resources.py` (run once after every `pip install`, and baked into `backend/Dockerfile`) copies them to wherever orthonym actually got installed — it locates the target via `sysconfig`, not by guessing a venv layout, so it works the same locally and in a container.

**This is not just packaging hygiene.** Without a live JVM (jpype + a JRE) and these two jars, Orthonym's SELF-01 self-consistency gate — the check that verifies a candidate name actually round-trips back to the right structure — silently **fails open**: confirmed by direct testing, a molecule that should honestly report as a lower-confidence `fallback` instead shipped as an unverified `pin`. `JPype1` is in `requirements.txt` and `backend/Dockerfile` installs `default-jre-headless` for exactly this reason. If you ever strip either out "to slim the image," re-run the regression check below first.

**Regression check** (should return `"status":"fallback"`, never `"status":"pin"`, for the second molecule):

```bash
curl -s -X POST http://localhost:8000/api/translate -H "Content-Type: application/json" -d \
  '{"smiles":["CCO","C1CC2CCC1(CC2)C3CCC4(CCC5(CCCC5C4C3)C)C"]}'
```

## Stopping

```bash
docker compose down
```
