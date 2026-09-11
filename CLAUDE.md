# CLAUDE.md

## What this is

Orthonym is the web app for **Orthonym**, a deterministic, rule-based SMILES→IUPAC naming engine.
It is not STOUT-V2: that neural model is a separate, unrelated project.

Stack: React 19 + Vite frontend; FastAPI + Celery + Redis + RDKit + Orthonym + OPSIN (JPype on a
real JRE) backend. No database, no auth. Naming runs in Celery workers; Redis is the broker, the job
store, the shared name cache and the rate-limit counters at once.

**This repository does not contain the naming engine.** `backend/vendor/` is populated from a
checkout of Orthonym, which is not public — see "The engine is not in this repo" below. A fresh
clone builds the frontend and the API shell; it cannot name a molecule until the engine is vendored
in.

## Commands

```bash
# Redis first — everything below needs it, tests included.
docker compose up -d redis           # container orthonym-redis, localhost:6379

# tests — from the repo root; this script is the only correct way to run them
backend/scripts/run-tests.sh                              # full suite
backend/scripts/run-tests.sh tests/test_name_spans.py -v  # one file

# backend — from backend/, three processes in three terminals
REDIS_URL=redis://localhost:6379/0 .venv/bin/python -m uvicorn app.main:app --port 8001
REDIS_URL=redis://localhost:6379/0 .venv/bin/python -m celery -A app.celery_app worker -Q fast  -c 2 -n fast@%h
REDIS_URL=redis://localhost:6379/0 .venv/bin/python -m celery -A app.celery_app worker -Q batch -c 2 -n batch@%h

# ad hoc scripts importing app.*
cd backend && PYTHONPATH="$(pwd)" REDIS_URL=redis://localhost:6379/0 .venv/bin/python <script.py>

# explain coverage census -- 544 names, prints the per-axis table. Runs the
# interpreter directly (not via run-tests.sh, which is for pytest only); the
# interpreter is backend/.venv/bin/python -- run-tests.sh itself now
# auto-detects .venv-mac (macOS) or .venv (Linux) and picks whichever exists.
cd backend && PYTHONPATH="$(pwd)" REDIS_URL=redis://localhost:6379/0 \
  .venv/bin/python scripts/explain_census.py

# frontend — from frontend/
npm run dev        # proxies /api -> http://localhost:8000
npm run build
npm test           # node --test over src/**/*.test.js; `node --test src/lib/` globs non-test files
npx oxlint src/    # `npm run lint` also lints vendored public/standalone/, which has old warnings

# whole stack: frontend :8080, backend 127.0.0.1:8000, redis, worker-fast, worker-batch
docker compose up -d --build
```

## The engine is not in this repo

`backend/vendor/` holds **three** pieces, not four: `orthonym/` (the engine source) and
`opsin-resources/` (the OPSIN grammar resources plus the `opsin-cli` jar) are populated by
`scripts/vendor-orthonym.sh` out of an Orthonym checkout and are gitignored wholesale, because
publishing them would publish the engine; `cdk/` holds only a tracked `NOTICE` — no jar is vendored
there at all. `centres-cli` is not vendored anywhere any more (`scripts/vendor-orthonym.sh:105-106`);
see below.

```bash
ORTHONYM_SRC=/path/to/Orthonym/Project ./scripts/vendor-orthonym.sh
```

Then bump `_KEY_VERSION` in `backend/app/name_cache.py` by hand. Upstream develops on a static
version `1.0.0`, so version-keyed cache invalidation cannot fire on its own and a name computed by
the old engine would survive the refresh.

**CDK**, and since 2026-09-07 **centres** as well, are FETCHED, not vendored: both release
jars have public URLs, so `backend/Dockerfile` downloads each at build time and checks it against a
pinned SHA-256 (CDK's is recorded in the tracked `backend/vendor/cdk/NOTICE`; centres' is a
`CENTRES_SHA256` build arg in the Dockerfile itself, there being no tracked NOTICE for it).
`backend/.dockerignore` keeps any local copy out of the build context, so a build here exercises the
same download path a fresh clone does. Centres used to be committed as a jar because the pinned
build was an unreleased snapshot (`develop @ d4b3cf0`) nobody could reproduce; the engine moved to
the tagged `1.2.1` release, which is fetchable the same way CDK's always was.

Without a live JVM and those jars, Orthonym's SELF-01 self-consistency gate **fails open**: a
molecule that should report as a lower-confidence `fallback` ships as an unverified `pin`. That is
why `app/jvm_guard.py` refuses rather than degrades, and why the Dockerfile proves the gate at build
time.

## Gotchas

Things the repo does not tell you, or tells you only after they cost time.

**Environment**
- `REDIS_URL` defaults to `redis://redis:6379/0`, the compose hostname. Outside compose, set
  `redis://localhost:6379/0`.
- Port 8000 may be Orthonym's own compose backend or another project's container. Run a manual backend
  on 8001; `vite.config.js` proxies to 8000, so repoint it for a browser check and revert.
- Docker Desktop stops on its own. A 502 through the Vite proxy plus a `docker.sock` error means the
  daemon is down, not the code.

**Tests**
- Only `backend/scripts/run-tests.sh`. A bare `pytest` prints a correct summary and then hangs about
  10 minutes because JPype's JVM will not let the process exit. Script exit codes: 0 passed,
  1 failed, 2 no summary (a real hang).
- The suite needs Redis; `conftest.py` fails with instructions instead of skipping.
- Kill every Celery worker first: `pkill -9 -f "celery -A app.celery_app"`, and
  `docker stop orthonym-worker-fast orthonym-worker-batch` when compose is up, because `pkill` does not
  reach containers. A live worker consumes the jobs the tests submit and the concurrency-cap tests
  then fail on correct code.
- Tests share the Redis DB with manual runs and are not namespaced. Leftover keys fail
  `test_rate_limit.py` and `test_jobs_api.py` on unmodified code; check
  `docker exec orthonym-redis redis-cli --scan --pattern 'orthonym:*' | wc -l` and `FLUSHDB` before
  trusting a before/after.

**Backend**
- uvicorn alone is not a backend: `/api/health` reports `DEGRADED` and every naming endpoint 503s
  until a worker records a live JVM. This is deliberate — see the SELF-01 note above.
- Do not call `startJVM`, and do not reorder the CDK/centres jar URLs; `cdk_bridge.py`'s docstring
  explains what each measured. `cdk_bridge.self_check()` asserts on the answer (L-alanine labelled
  `S`) because a CIP pass that stops labelling still returns a good SVG.
- JVM, font and native-library checks that pass on macOS can fail inside the slim Debian image and
  degrade silently (CDK drew nothing, RDKit fallback hid it). Probe inside the built container.
- Redis runs `volatile-lru`, not `allkeys-lru`, because broker messages carry no TTL. Rate limits are
  per IP; the `127.0.0.1` binding and `TRUST_PROXY_HEADERS` are a pair and neither is safe alone.
  Both reasons are in `docker-compose.yml`.
- Deployment profiles are `backend/config/{small,medium,large}.yml`, selected by
  `DEPLOYMENT_PROFILE`. Precedence env > profile > code default is hand-implemented in
  `backend/app/core/config.py` because pydantic-settings' order is the opposite. Profiles must stay
  under `backend/`, the Docker build context.
- `SoftTimeLimitExceeded` subclasses `Exception` directly, so a per-molecule `except Exception`
  swallows it. Celery's `Signal.send` catches and discards exceptions from handlers; only
  `SystemExit` stops a worker booting.

**Frontend**
- Seven routes (`/`, `/from-name`, `/explain`, `/about`, `/imprint`, `/privacy`, `/terms`) plus
  redirects and a `*` catch-all, all in `App.jsx`. Home uses the `.workbench` shell, `/from-name` and
  `/explain` use `.workspace`, `/about` uses `.chart`, and the three legal pages use `.legal`. There
  is exactly one `.workspace` rule in `App.css`; a second copy is a stale leftover that wins the
  cascade.
- **Page stylesheets are imported BEFORE `./App.css` in `App.jsx`**, so a page rule at equal
  specificity *loses* to App.css. Two overrides in `pages/Legal.css` shipped dead because of this;
  they are `.prose.legal-prose` and `.page-hero.page-hero--legal` for that reason. Measure an
  override in the browser before believing it.
- `components/Icon.jsx` returns `null` for an unknown icon name, silently.
- `frontend/node_modules` may hold only Linux native bindings; a fresh worktree needs its own
  `npm install`.
- Verify layout in the loaded state (results on screen, a job running) and by screenshot.
  `getComputedStyle` asserts what CSS declares, not what renders — and it cannot see a composited
  gradient at all, so sample real pixels for contrast on the page ground. Settle transitions before
  measuring.
- Contrast on translucent fills must clear AA twice: at the fill and again under the `::before`
  highlight. Chrome reports `color(srgb 0.76 0.11 0.22 / 0.9)` with fractional channels; a 0-255
  parser reports nonsense ratios.
- An absolutely-positioned element contributes to document scroll height even when invisible.
  Home's closed INFO drawer did exactly that — an invisible 683px box gave every visitor a scrollbar
  over empty ground. `content-visibility: hidden` fixes it; `height: 0` does not, because
  `overflow: visible` children keep contributing.
- An effect keyed on a payload string does not re-run when the DOM node it writes into is replaced.
  `useAtomHighlight` uses a callback ref in state so the node itself is a dependency; keying on
  `data.svg` meant re-submitting the same molecule left an empty frame.

**Product truth**
- Confidence tiers (verified PIN, verified fallback, best-effort, abstain, error) are the product.
  Each is a rule under the name plus a plain-text label, never conflated, and never reduced to a
  word in a column.
- **A tier lamp (`components/TierLamp.jsx`) adds colour, and the ladder inside it is FORM, not
  hue.** Each lamp wears its own tier's rule pattern: double ring, dashed, dotted, plain unlit,
  struck. The reason is measured, not stylistic -- a pure hue ramp separates adjacent tiers by only
  1.03-1.11:1 under deuteranopia, so hue may reinforce a signal and can never be one. The rule and
  the label both stay, so no reading depends on colour, and the lamp is `aria-hidden`. Palette:
  `--success` / `--olive` (the verified pair share one green family on purpose; the ring pattern
  separates them), `--accent-amber`, `--muted`, and `--tier-stop` for an error. **The crimson
  `--accent` still never touches a tier** -- that is what `--tier-stop` exists for, and fixing
  `.results-group--error`, which had been colouring the error tier crimson, was part of the same
  change. In a payload, `tier` moves with `status`.
- The rendered chemical name is never uppercased or bolded; IUPAC case and weight are semantic.
- The rendered name IS typeset the way IUPAC prints it: italic stereodescriptors, element-symbol
  locants, `tert-`, indicated hydrogen and fusion letters; superscript bridge locants; subscript
  formula counts. `lib/nameTypography.js` decides which characters, `components/Typeset.jsx` renders
  them, and all seven name surfaces go through it. Display only — the string is never rewritten, and
  every copy/CSV/SDF path reads the data object, so the caret of `0^4,9` still leaves the page.
- `/from-name` computes no tier and no verdict: OPSIN either parses a name or does not, and borrowing
  Home's grammar there would claim a check that never ran.
- `/explain` explains **how the name is written**: every name token that teaches something is its
  own hoverable child with its own plain-language line. Token children are referential -- OPSIN
  gives a fused ring ONE atom set, so `[a]` cannot own atoms and inherits its parent's highlight.
  Spans are DERIVED from token offsets (`app/name_tokens.py`), never searched for by text. If the
  token run cannot be accounted for, the name withholds EVERY span rather than guess. Coverage is
  measured, not assumed: `backend/scripts/explain_census.py` classifies all 544 names and prints
  the residue rather than hiding it, and `backend/tests/test_explain_coverage.py` gates a curated
  subset of that corpus so a class already fixed cannot silently regress. This is **not**
  near-total coverage -- measured 2026-09-11, 277 of 544 names decompose cleanly, 157 are still
  fully inert (`SPANS_NONE`), and the rest are partially spanned; the residue is real and named,
  not accidental (lossy OPSIN labels where a duplicated token means the part text is no longer a
  substring of the name, plus a text-grouped-substituent class worth a measured +55 names that a
  follow-on project owns, not this one).
- The three legal pages describe **this deployment**, and every factual claim in `Privacy.jsx` was
  read out of the backend or measured against a running stack. Do not adapt wording from another
  site's policy: a policy that claims processing which does not happen is as wrong as one that hides
  processing which does. The header comment in each page records what was verified and how.

## Scope

Do the task asked. When you find an unrelated bug or a tempting cleanup, list it in your report; the
maintainer decides whether it becomes work.

## Product principles

1. Determinism is proven, not asserted: the OPSIN round-trip line is visible on every named tile.
2. Accuracy is never overstated: cite the version, the benchmark and the metric's definition.
3. PIN vs fallback vs best-effort is visible wherever a name appears, never a footnote.
4. Image→SMILES (OCSR) is the one permanent exclusion.
