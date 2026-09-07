# STITCH

**S**MILES **T**O **I**UPAC name **T**ranslator for **CH**emistry — a web app putting OpenSTOUT's
deterministic, rule-based naming engine in front of visitors. Every name it shows carries the
confidence STITCH could actually claim for it: a verified PIN, a verified fallback, a best effort, or
an honest abstention.

> **This repository does not contain the naming engine.** `backend/vendor/` is populated from a
> checkout of OpenSTOUT, which is not public. A fresh clone builds and runs the frontend and the API
> shell, but cannot name a molecule until the engine is vendored in — see
> [The OpenSTOUT dependency](#the-openstout-dependency).

## Architecture in one paragraph

The backend is **not a single process**. A FastAPI web process answers requests, but every name is
computed in a **Celery worker** that holds its own JVM for OPSIN, and **Redis** carries the Celery
broker, job results, a shared name cache and the per-IP rate-limit counters. Requests of **10
molecules or fewer** are answered inline; anything larger becomes a **job** the caller polls. A web
process with no worker behind it answers `/api/health` with `DEGRADED` and returns **503** from every
naming endpoint — deliberately, because OpenSTOUT's SELF-01 verification fails *open* (see below).

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

## Deploying it publicly

`docker compose up -d` is the whole deployment, but three things about it are only correct
because of decisions recorded elsewhere, and all three break quietly rather than loudly.

### Put a TLS terminator in front — and let it forward the client address

`frontend` is the only service published beyond loopback, and it speaks **plain HTTP on 8080**.
A public host needs something holding the certificate for the real hostname in front of it.
Anything works; the requirement is the header:

```nginx
# on the TLS terminator
location / {
    proxy_pass http://127.0.0.1:8080;
    proxy_set_header Host              $host;
    proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;   # <- not optional
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

(Caddy sets `X-Forwarded-For` itself, so a bare `reverse_proxy 127.0.0.1:8080` is enough.)

Without that header every visitor collapses into a single per-IP rate-limit bucket and one
script 429s the whole site. `frontend/nginx.conf`'s `set_real_ip_from` block recovers the true
address and carries the full reasoning; narrow its four ranges if the terminator has a fixed
address.

HSTS belongs on the terminator, not in `frontend/nginx.conf` — a `Strict-Transport-Security`
header sent over plain HTTP is ignored, and that container never speaks TLS.

### The memory dials

Every service has a `mem_limit`, overridable from `.env` as `WORKER_MEM_LIMIT` (`3g`),
`REDIS_MEM_LIMIT` (`3g`), `BACKEND_MEM_LIMIT` (`1500m`) and `FRONTEND_MEM_LIMIT` (`256m`). Each
sits beside a comment in `docker-compose.yml` saying what it is sized from and when to raise it;
the two that bite are the worker limit (arithmetic off `OPENSTOUT_JVM_XMX` × concurrency) and the
redis limit (must stay **above** `REDIS_MAXMEMORY`, never equal).

### What "healthy" means here

```bash
docker compose ps        # every service should read (healthy)
```

A backend reporting healthy while `/api/health` says `DEGRADED` is correct, not a bug: it is
refusing names because no worker has a live JVM. Each check's scope, and what it deliberately
does **not** prove, is commented at the check itself in `docker-compose.yml`.

Logs are capped at 10 MB × 3 files per service; the Docker default is unbounded, and the workers
log a line per molecule.

## Run locally without Docker

You need **four** processes, not two. Redis first:

```bash
docker compose up -d redis    # service stitch-redis, publishes localhost:6379
```

```bash
# backend — from backend/. uv, not `python3.12 -m venv`: there is no
# `python3.12` on PATH on a typical dev Mac here, and uv fetches its own.
uv venv --python 3.12 .venv && source .venv/bin/activate
uv pip install -r requirements.txt        # `pip` itself is not in this venv
python scripts/place_opsin_resources.py   # see "OpenSTOUT dependency" below — required.
                                          # Not automatic: the vendored openstout is a plain
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
docker compose up -d redis           # required — the suite fails with instructions without it
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
| `POST /api/jobs/{id}/cancel` | Stop a running job and free its concurrent slot |
| `DELETE /api/jobs/{id}` | Discard a finished job |

**Cancel and delete need the job's `owner_token`**, returned once in the response that created
the job. A results URL carries the job id but not the token, so sharing results does not hand over
the ability to delete them. Pass it as a query parameter:
`POST /api/jobs/{id}/cancel?owner_token=...`.

Cancellation is cooperative: chunks not yet started stop immediately, and one already running
finishes that chunk (at most `BATCH_CHUNK_SIZE` molecules) because a running task cannot be
interrupted mid-molecule.

Upload size and molecule count **are** profile-dependent: **2,000 molecules / 20 MB** (`small`),
**10,000 / 50 MB** (`medium`, the default), **50,000 / 200 MB** (`large`).

Everything else is a code default, **not** profile-driven, though each is overridable by
environment variable: results live **24 h**, the shared name cache lives **7 days**, and the per-IP
caps are **2** concurrent jobs, **20** jobs/hour, **60** naming requests/min, **300** polls/min,
**1200** depictions/min.

## The OpenSTOUT dependency

OpenSTOUT isn't published on PyPI in the form STITCH needs (`name_tiered()`, `general_fallback`), so
`backend/requirements.txt` installs it from `backend/vendor/openstout` — a snapshot, not a live path
dependency, so a container build never has to reach outside its own context.

**That snapshot is not in this repository, and neither are three of the four vendored artifacts.**
`scripts/vendor-openstout.sh` copies all of them out of an OpenSTOUT checkout: the engine source, the
OPSIN grammar resources, and the `opsin-cli` and `centres-cli` jars. Publishing them would publish
the engine, so all four are gitignored. Run the script before your first build:

```bash
OPENSTOUT_SRC=/path/to/OpenSTOUT/Project ./scripts/vendor-openstout.sh
```

The exception is **CDK**, the only vendored artifact with a public release URL: `backend/Dockerfile`
downloads it during the build and checks it against the SHA-256 recorded in
`backend/vendor/cdk/NOTICE`, which is tracked. `backend/.dockerignore` keeps any local copy out of
the build context, so a build here exercises the same download path a fresh clone does. `centres-cli`
cannot be fetched at all — its notice records it as a local Maven build from an unreleased commit.

**Refresh the snapshot** after pulling OpenSTOUT changes you want STITCH to pick up:

```bash
OPENSTOUT_SRC=/path/to/OpenSTOUT/Project ./scripts/vendor-openstout.sh
```

Then **bump `_KEY_VERSION` in `backend/app/name_cache.py` by hand.** Upstream develops on a static
version `1.0.0`, so the version-keyed cache invalidation cannot fire on its own and a name computed
by the old engine would survive the refresh.

### The part that isn't optional: SELF-01 needs a real JVM

OpenSTOUT ships three modules that each compute an identical `PROJECT_ROOT` (4 parents up from their own installed file) and expect real artifacts sitting there as siblings of `src/` in a full dev checkout:

| Module | Expects |
|---|---|
| `validation/opsin_grammar.py` | `opsin/opsin-core/src/main/resources/...` |
| `validation/opsin_roundtrip.py` | `opsin-cli-2.9.0-jar-with-dependencies.jar` |
| `perception/centres_bridge.py` | `centres-cli-1.5.jar` |

None of these ship with the pip package. `scripts/vendor-openstout.sh` vendors all three into `backend/vendor/opsin-resources/`, and `backend/scripts/place_opsin_resources.py` (run once after every `pip install`, and baked into `backend/Dockerfile`) copies them to wherever openstout actually got installed — it locates the target via `sysconfig`, not by guessing a venv layout, so it works the same locally and in a container.

**This is not just packaging hygiene.** Without a live JVM (jpype + a JRE) and these two jars, OpenSTOUT's SELF-01 self-consistency gate — the check that verifies a candidate name actually round-trips back to the right structure — silently **fails open**: confirmed by direct testing, a molecule that should honestly report as a lower-confidence `fallback` instead shipped as an unverified `pin`. `JPype1` is in `requirements.txt` and `backend/Dockerfile` installs `default-jre-headless` for exactly this reason. If you ever strip either out "to slim the image," re-run the regression check below first.

That failure mode is why `app/jvm_guard.py` refuses rather than degrades: if no worker reports a live
JVM, every naming endpoint — including `POST /api/jobs` — returns 503 instead of serving names with
an unverified confidence tier.

### The third jar: CDK draws every picture

`backend/vendor/cdk/cdk-2.12.jar` (42 MB, LGPL — see its `NOTICE`) is the **default depiction
engine**. It annotates **CIP stereo descriptors** onto the drawing — `(R)`/`(S)`, `(E)`/`(Z)`, and
`(?)` for a stereocentre the input leaves undefined — which is the reason it replaced RDKit's
drawing. RDKit remains the fallback for any process where the JVM will not come up. CDK is also a
**second SMILES parser**: a string RDKit refuses is offered to it before the input is called
unreadable.

It is **not on the JVM's classpath**, and cannot be: OpenSTOUT owns the only `startJVM` call and
boots with a fixed one. `app/cdk_bridge.py` loads it in an isolated `java.net.URLClassLoader`
instead — read that module's docstring before changing anything about it, especially the parent
loader and the URL order, both of which are load-bearing and both of which fail in ways that look
like something else.

**`default-jre-headless` alone is not enough for this**, and the way it fails is the point:
`fontconfig`, `libfreetype6`, `libharfbuzz0b` and `fonts-dejavu-core` must be installed too, or
`libfontmanager.so` cannot load, only the *draw* step dies, and the app silently serves RDKit
pictures with no stereo labels. Nothing looks broken from the outside. `backend/Dockerfile`
installs all four.

**Regression check for CDK** (run it after any jar bump, JRE change, or image slimming):

```bash
docker compose run --rm --entrypoint sh backend -c \
  'python -c "from app import cdk_bridge as c; print(c.self_check(), c.cip_labels(\"C[C@H](N)C(=O)O\"))"'
# must print:  True ['S']
```

`self_check()` asserts on the ANSWER — L-alanine must come back labelled `S` — not merely on the
absence of an exception, because a CIP pass that stopped labelling still returns a perfectly good
SVG. Each Celery child runs it at boot and logs the verdict.

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
