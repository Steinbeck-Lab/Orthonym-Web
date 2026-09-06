# CLAUDE.md

## What this is

STITCH is the public showcase web app for **OpenSTOUT**, a deterministic, rule-based SMILES→IUPAC
naming engine (private upstream `github.com/Kohulan/OpenSTOUT`, vendored as a snapshot under
`backend/vendor/openstout`). It is not STOUT-V2: that neural model has its own unrelated sibling
repo, `~/STOUT_WebApp` (Vue 3). Shells open there by mistake, so check `pwd` before editing.

Stack: React 19 + Vite frontend; FastAPI + Celery + Redis + RDKit + OpenSTOUT + OPSIN (JPype on a
real JRE) backend. No database, no auth. Naming runs in Celery workers; Redis is the broker, the job
store, the shared name cache and the rate-limit counters at once.

The detail lives in files you load when you need them:

- `DESIGN.md` — the shipped visual system and every load-bearing CSS decision with its reason. Read it before a visual change; `.impeccable/design.json` is its token sidecar, keep both in sync.
- `PRODUCT.md` — the four product principles (summarised at the end of this file).
- `docs/architecture-notes.md` — backend and frontend internals with the measured numbers: job layer, confidence tiers, the verify switch, `/from-name`, name cache, CDK.
- `backend/app/cdk_bridge.py` docstring — why CDK loads through its own classloader and in which jar order.
- `docker-compose.yml` comments — the Redis eviction policy, and the `127.0.0.1` binding + `TRUST_PROXY_HEADERS` pair.
- `README.md` "Regression check" — the SELF-01 fail-open check to run after any JRE, jar or image change.

## Commands

```bash
# Redis first — everything below needs it, tests included.
docker compose up -d redis           # container stitch-redis, localhost:6379

# tests — from the repo root; this script is the only correct way to run them
backend/scripts/run-tests.sh                              # full suite
backend/scripts/run-tests.sh tests/test_name_spans.py -v  # one file

# backend — from backend/, three processes in three terminals
REDIS_URL=redis://localhost:6379/0 .venv-mac/bin/python -m uvicorn app.main:app --port 8001
REDIS_URL=redis://localhost:6379/0 .venv-mac/bin/python -m celery -A app.celery_app worker -Q fast  -c 2 -n fast@%h
REDIS_URL=redis://localhost:6379/0 .venv-mac/bin/python -m celery -A app.celery_app worker -Q batch -c 2 -n batch@%h

# ad hoc scripts importing app.*
cd backend && PYTHONPATH="$(pwd)" REDIS_URL=redis://localhost:6379/0 .venv-mac/bin/python <script.py>

# frontend — from frontend/
npm run dev        # proxies /api -> http://localhost:8000
npm run build
npm test           # node --test over src/**/*.test.js; `node --test src/lib/` globs non-test files
npx oxlint src/    # `npm run lint` also lints vendored public/standalone/, which has old warnings

# whole stack: frontend :8080, backend 127.0.0.1:8000, redis, worker-fast, worker-batch
docker compose up -d --build
```

## Gotchas

Things the repo does not tell you, or tells you only after they cost time.

**Environment**
- Address paths absolutely, not with `cd`. `cd <dir> && grep -rn x app/` prompts for approval every time: a relative path after a `cd` resolves to a directory the permission check cannot determine, so with any `Read()` deny rule configured it cannot prove the search misses a denied file. `grep -rn x /abs/path/app/` is the identical search and runs unprompted. Same for git — `git -C <dir> status`, never `cd <dir> && git status`, because a `cd` into a different directory before `git` always prompts (that directory's hooks could run).
- `backend/.venv` is a Linux venv with a dangling `python` symlink. Use `backend/.venv-mac/bin/python`. It has no `pip`: install with `uv pip install -r requirements.txt`. Its console shims (`celery`, `pytest`, `uvicorn`) work.
- `REDIS_URL` defaults to `redis://redis:6379/0`, the compose hostname. Outside compose, set `redis://localhost:6379/0`.
- Port 8000 may be STITCH's own compose backend or another project's container. Run a manual backend on 8001; `vite.config.js` proxies to 8000, so repoint it for a browser check and revert.
- `.env` and `.env.*` are unreadable by a user-global deny rule, anchored at the filesystem root (`Read(//**/.env)`) so it holds whatever the working directory is. Hand the text to the owner instead of loosening the rule.
- Playwright is an MCP server, not a local install. Its browser is shared: a subagent can navigate it away or resize it mid-measurement.
- Docker Desktop stops on its own. A 502 through the Vite proxy plus a `docker.sock` error means the daemon is down, not the code.

**Tests**
- Only `backend/scripts/run-tests.sh`. A bare `pytest` prints a correct summary and then hangs about 10 minutes because JPype's JVM will not let the process exit. Script exit codes: 0 passed, 1 failed, 2 no summary (a real hang).
- The suite needs Redis; `conftest.py` fails with instructions instead of skipping.
- Kill every Celery worker first: `pkill -9 -f "celery -A app.celery_app"`, and `docker stop stitch-worker-fast stitch-worker-batch` when compose is up, because `pkill` does not reach containers. A live worker consumes the jobs the tests submit and the concurrency-cap tests then fail on correct code.
- Tests share the Redis DB with manual runs and are not namespaced. Leftover keys fail `test_rate_limit.py` and `test_jobs_api.py` on unmodified code; check `docker exec stitch-redis redis-cli --scan --pattern 'stitch:*' | wc -l` and `FLUSHDB` before trusting a before/after.

**Backend**
- uvicorn alone is not a backend: `/api/health` reports `DEGRADED` and every naming endpoint 503s until a worker records a live JVM. This is deliberate. Without a JVM, OpenSTOUT's SELF-01 round-trip gate fails open and a `fallback` ships labelled `pin`.
- Do not call `startJVM`, and do not reorder the CDK/centres jar URLs; `cdk_bridge.py`'s docstring explains what each measured. `cdk_bridge.self_check()` asserts on the answer (L-alanine labelled `S`) because a CIP pass that stops labelling still returns a good SVG.
- JVM, font and native-library checks that pass on macOS can fail inside the slim Debian image and degrade silently (CDK drew nothing, RDKit fallback hid it). Probe inside the built container.
- Refresh the OpenSTOUT snapshot with `scripts/vendor-openstout.sh` from a fresh clone: `gh repo clone Kohulan/OpenSTOUT <dir> -- --depth 1`. The local checkout at `/Volumes/Data_Drive/My_Projects/2026/OpenSTOUT/Project` reports `0.1.0` and would downgrade the vendored `1.0.0`. Upstream has no tags; `name_cache._engine_fingerprint()` hashes the installed source so a refresh invalidates the cache.
- Redis runs `volatile-lru`, not `allkeys-lru`, because broker messages carry no TTL. Rate limits are per IP; the `127.0.0.1` binding and `TRUST_PROXY_HEADERS` are a pair and neither is safe alone. Both reasons are in `docker-compose.yml`.
- Deployment profiles are `backend/config/{small,medium,large}.yml`, selected by `DEPLOYMENT_PROFILE`. Precedence env > profile > code default is hand-implemented in `backend/app/core/config.py` because pydantic-settings' order is the opposite. Profiles must stay under `backend/`, the Docker build context.
- `SoftTimeLimitExceeded` subclasses `Exception` directly, so a per-molecule `except Exception` swallows it. Celery's `Signal.send` catches and discards exceptions from handlers; only `SystemExit` stops a worker booting.

**Frontend**
- Four pages (`/`, `/from-name`, `/explain`, `/about`) plus redirects, all in `App.jsx`. Home uses the `.workbench` shell; the others use `.workspace`. There is exactly one `.workspace` rule in `App.css`; a second copy is a stale leftover that wins the cascade.
- `components/Icon.jsx` returns `null` for an unknown icon name, silently.
- `frontend/node_modules` may hold only Linux native bindings; a fresh worktree needs its own `npm install`.
- Verify layout in the loaded state (results on screen, a job running) and by screenshot. `getComputedStyle` asserts what CSS declares, not what renders. Settle transitions before measuring.
- Contrast on translucent fills must clear AA twice: at the fill and again under the `::before` highlight. Chrome reports `color(srgb 0.76 0.11 0.22 / 0.9)` with fractional channels; a 0-255 parser reports nonsense ratios.

**Product truth**
- Confidence tiers (verified PIN, verified fallback, best-effort, abstain, error) are the product. Each is a monochrome rule under the name, is never coloured with the crimson chrome accent, never conflated, and never reduced to a word in a column. In a payload, `tier` moves with `status`.
- The rendered chemical name is never uppercased or bolded; IUPAC case and weight are semantic.
- The rendered name IS typeset the way IUPAC prints it (2026-09-06): italic stereodescriptors,
  element-symbol locants, `tert-`, indicated hydrogen and fusion letters; superscript bridge locants;
  subscript formula counts. `lib/nameTypography.js` decides which characters, `components/Typeset.jsx`
  renders them, and all seven name surfaces go through it. Display only — the string is never rewritten,
  and every copy/CSV/SDF path reads the data object, so the caret of `0^4,9` still leaves the page.
- About cites **94.8%** round-trip exact match, 0 wrong structures, 1,500 ChEBI+PubChem molecules, OpenSTOUT v1.0.0, on purpose. The vendored README now says 96.1%. Raising the site's figure is the owner's call; ask.
- `/from-name` computes no tier and no verdict: OPSIN either parses a name or does not, and borrowing Home's grammar there would claim a check that never ran.
- Choices that look arbitrary (light theme, sans body, all-crimson glossy buttons, bandless footer, a Health Check that is a board on About) are owner instructions with reasons in `DESIGN.md`. If one seems wrong, say so and let the owner decide.

## Scope

Do the task asked. When you find an unrelated bug or a tempting cleanup, list it in your report; the owner decides whether it becomes work.

## Product principles (from `PRODUCT.md`)

1. Determinism is proven, not asserted: the OPSIN round-trip line is visible on every named tile.
2. Accuracy is never overstated: cite the version, the benchmark and the metric's definition.
3. PIN vs fallback vs best-effort is visible wherever a name appears, never a footnote.
4. Image→SMILES (OCSR) is the one permanent exclusion; everything else in STOUT_WebApp is fair to borrow as a UX reference.
