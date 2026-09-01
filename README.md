# Orthonym

Verified IUPAC names for Chemical Structures — a public prototype putting [Orthonym](https://github.com/Kohulan/Orthonym)'s deterministic, rule-based naming engine in front of visitors. See `PRODUCT.md` for product context and `DESIGN.md` for the visual system (a soft-grey card bento where confidence is a rule beneath the name, never a colour).

## Architecture in one paragraph

The backend is **not a single process**. A FastAPI web process answers requests, but every name is
computed in a **Celery worker** that holds its own JVM for OPSIN, and **Redis** carries the Celery
broker, job results, a shared name cache and the per-IP rate-limit counters. Requests of **10
molecules or fewer** are answered inline; anything larger becomes a **job** the caller polls. A web
process with no worker behind it answers `/api/health` with `DEGRADED` and returns **503** from every
naming endpoint — deliberately, because Orthonym's SELF-01 verification fails *open* (see below).

## Run with Docker (recommended)

```bash
docker compose up -d --build
```

Five containers come up: `redis`, `backend`, `worker-fast`, `worker-batch`, `frontend`.

- Frontend: http://localhost:8080
- Backend: http://127.0.0.1:8000 (docs at `/docs`) — loopback only, on purpose; see the comment
  block in `docker-compose.yml`, where the port binding and `TRUST_PROXY_HEADERS` are a pair and
  neither is safe alone.

**Wait for a worker before testing.** The workers each boot a JVM and then record that they have one.
Until at least one has, naming is refused:

```bash
curl -s http://127.0.0.1:8000/api/health
# {"status":"OK","opsin":"available"}   <- ready
# {"status":"DEGRADED","opsin":"no worker has a live JVM"}  <- wait, or check worker logs
```

### Sizing

`DEPLOYMENT_PROFILE` (`small` | `medium` | `large`, default `medium`) selects a profile from
`backend/config/`. Precedence is **environment variable > profile > code default**. Each profile sets
exactly six keys — `CELERY_WORKERS_FAST`, `CELERY_WORKERS_BATCH`, `REDIS_MAXMEMORY`,
`BATCH_CHUNK_SIZE`, `MAX_BATCH_SIZE`, `MAX_FILE_SIZE_MB`. It does **not** set the rate limits or the
TTLs; those are code defaults you override by environment variable. Copy `.env.example` to `.env` for
that.

One wrinkle worth knowing: with `DEPLOYMENT_PROFILE` unset, `core/config.py` applies **no** profile at
all rather than falling back to `medium`. That is harmless only because the code defaults happen to
equal `medium.yml`'s values — compose always sets it explicitly.

## Run locally without Docker

You need **four** processes, not two. Redis first:

```bash
docker start orthonym-redis-dev    # or: docker run -d --name orthonym-redis-dev -p 6379:6379 redis:7-alpine
```

```bash
# backend — from backend/. uv, not `python3.12 -m venv`: there is no
# `python3.12` on PATH on a typical dev Mac here, and uv fetches its own.
uv venv --python 3.12 .venv-mac && source .venv-mac/bin/activate
uv pip install -r requirements.txt        # `pip` itself is not in this venv
python scripts/place_opsin_resources.py   # see "Orthonym dependency" below — required.
                                          # Not automatic: the vendored orthonym is a plain
                                          # hatchling package with no build hook, so pip will
                                          # not run it for you.

# terminal 1 — web process
REDIS_URL=redis://localhost:6379/0 python -m uvicorn app.main:app --host 0.0.0.0 --port 8001

# terminal 2 — interactive worker (this is what makes naming work at all)
REDIS_URL=redis://localhost:6379/0 python -m celery -A app.celery_app worker -Q fast -c 2 -n fast@%h

# terminal 3 — batch worker (only needed for jobs > 10 molecules)
REDIS_URL=redis://localhost:6379/0 python -m celery -A app.celery_app worker -Q batch -c 2 -n batch@%h
```

```bash
# frontend (terminal 4) — from frontend/
npm install
npm run dev   # proxies /api -> http://localhost:8000
```

Two things that will bite:

- **`REDIS_URL` defaults to `redis://redis:6379/0`**, the compose-internal hostname, which does not
  resolve outside compose. Every command above overrides it; ad hoc scripts must too.
- **Port 8001, and the vite proxy points at 8000.** For a real browser check, repoint
  `frontend/vite.config.js` at 8001 temporarily, then revert. Port 8000 is also frequently held by an
  unrelated container.

## Tests

```bash
docker start orthonym-redis-dev        # required — the suite fails with instructions without it
backend/scripts/run-tests.sh         # whole suite
backend/scripts/run-tests.sh tests/test_inputs.py -v
```

**Do not run a bare `pytest`.** JPype's JVM refuses to let the process exit, so a bare run looks like
a 10-minute hang ending in exit 144 — *after* it has already printed a correct summary. The script
waits for pytest's own summary line, kills the corpse, and exits `0` (passed) / `1` (failed) /
`2` (a real hang).

## The batch/job API

There is **no frontend UI for this yet**; it is reachable over the API.

| Endpoint | Purpose |
|---|---|
| `POST /api/jobs` | Upload `.sdf`, `.mol`, `.csv` (needs a `smiles` column), or a plain SMILES list |
| `POST /api/parse-preview` | Count an upload and sample-check its first few records, without dispatching it. Not a full validation — an empty `errors` means the sample was clean, not the file |
| `GET /api/jobs/{id}` | Progress |
| `GET /api/jobs/{id}/results` | Paged rows |
| `GET /api/jobs/{id}/results.csv` | Streamed CSV of the whole job |
| `DELETE /api/jobs/{id}` | Discard early |

Upload size and molecule count **are** profile-dependent: **2,000 molecules / 20 MB** (`small`),
**10,000 / 50 MB** (`medium`, the default), **50,000 / 200 MB** (`large`).

Everything else is a code default, **not** profile-driven, though each is overridable by
environment variable: results live **24 h**, the shared name cache lives **7 days**, and the per-IP
caps are **2** concurrent jobs, **20** jobs/hour, **60** naming requests/min, **300** polls/min,
**1200** depictions/min.

## The Orthonym dependency

Orthonym isn't published on PyPI in the form Orthonym needs (`name_tiered()`, `general_fallback`), so `backend/requirements.txt` installs it from `backend/vendor/orthonym` — a snapshot vendored from the local sibling project, not a live path dependency. This keeps Docker builds self-contained (a container can't reach outside its build context) and makes the backend reproducible without assuming an Orthonym checkout exists on the host it's built on.

**Refresh the snapshot** after pulling Orthonym changes you want Orthonym to pick up:

```bash
ORTHONYM_SRC=/path/to/Orthonym/Project ./scripts/vendor-orthonym.sh
```

Then **bump `_KEY_VERSION` in `backend/app/name_cache.py` by hand.** Upstream develops on a static
version `1.0.0`, so the version-keyed cache invalidation cannot fire on its own and a name computed
by the old engine would survive the refresh.

### The part that isn't optional: SELF-01 needs a real JVM

Orthonym ships three modules that each compute an identical `PROJECT_ROOT` (4 parents up from their own installed file) and expect real artifacts sitting there as siblings of `src/` in a full dev checkout:

| Module | Expects |
|---|---|
| `validation/opsin_grammar.py` | `opsin/opsin-core/src/main/resources/...` |
| `validation/opsin_roundtrip.py` | `opsin-cli-2.9.0-jar-with-dependencies.jar` |
| `perception/centres_bridge.py` | `centres-cli-1.5.jar` |

None of these ship with the pip package. `scripts/vendor-orthonym.sh` vendors all three into `backend/vendor/opsin-resources/`, and `backend/scripts/place_opsin_resources.py` (run once after every `pip install`, and baked into `backend/Dockerfile`) copies them to wherever orthonym actually got installed — it locates the target via `sysconfig`, not by guessing a venv layout, so it works the same locally and in a container.

**This is not just packaging hygiene.** Without a live JVM (jpype + a JRE) and these two jars, Orthonym's SELF-01 self-consistency gate — the check that verifies a candidate name actually round-trips back to the right structure — silently **fails open**: confirmed by direct testing, a molecule that should honestly report as a lower-confidence `fallback` instead shipped as an unverified `pin`. `JPype1` is in `requirements.txt` and `backend/Dockerfile` installs `default-jre-headless` for exactly this reason. If you ever strip either out "to slim the image," re-run the regression check below first.

That failure mode is why `app/jvm_guard.py` refuses rather than degrades: if no worker reports a live
JVM, every naming endpoint — including `POST /api/jobs` — returns 503 instead of serving names with
an unverified confidence tier.

**Regression check.** Confirm a worker is up first, or this returns 503 rather than a name:

```bash
curl -s http://127.0.0.1:8000/api/health          # must be {"status":"OK",...}

curl -s -X POST http://127.0.0.1:8000/api/translate -H "Content-Type: application/json" -d \
  '{"smiles":["CCO","C1CC2CCC1(CC2)C3CCC4(CCC5(CCCC5C4C3)C)C"]}'
```

The second molecule must come back `"status":"fallback"`, never `"status":"pin"`.

## Stopping

```bash
docker compose down
```
