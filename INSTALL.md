# Installing and running STITCH

Everything operational lives here: how to run it, how to deploy it, how to test it, and what the
engine dependency actually requires. The [README](README.md) is the short version.

> **Before anything else.** This repository does not contain the naming engine. `backend/vendor/`
> is populated from a checkout of OpenSTOUT, which is not public — see
> [The OpenSTOUT dependency](#the-openstout-dependency). A fresh clone builds and runs the
> frontend and the API shell, but cannot name a molecule until the engine is vendored in.

## Contents

- [Run with Docker (recommended)](#run-with-docker-recommended)
- [Deploying it publicly](#deploying-it-publicly)
- [Run locally without Docker](#run-locally-without-docker)
- [Tests](#tests)
- [The batch/job API](#the-batchjob-api)
- [The OpenSTOUT dependency](#the-openstout-dependency)
- [Stopping](#stopping)

---

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

## Deploying it publicly

`docker compose up -d` is the whole deployment, but three things about it are only correct
because of decisions recorded elsewhere, and all three break quietly rather than loudly.

### Put a TLS terminator in front — and let it forward the client address

`frontend` is the only service published beyond loopback, and it speaks **plain HTTP on 8080**.
A public host needs something holding the certificate for the real hostname in front of it.
Anything works; the requirement is the header:

```nginx

## Run locally without Docker

You need **four** processes, not two. Redis first:

```bash
docker compose up -d redis    # service stitch-redis, publishes localhost:6379
```

```bash

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
| `perception/centres_bridge.py` | `centres-cli-1.2.1.jar` (downloaded by the Dockerfile) |

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

## Stopping

```bash
docker compose down
```
