# CLAUDE.md

## What this is

Orthonym-Web is the web app for **the Orthonym engine**, a deterministic, rule-based SMILES→IUPAC
naming engine. It is not STOUT-V2: that neural model is a separate, unrelated project. In prose the
app is "Orthonym" and the engine "the Orthonym engine"; never write "ORTHONYM", which is only the
wordmark's CSS uppercasing.

Stack: React 19 + Vite frontend; FastAPI + Celery + Redis + RDKit + the Orthonym engine + OPSIN
(JPype on a real JRE) backend. No database, no auth. Naming runs in Celery workers; Redis is the
broker, the job store, the shared name cache and the rate-limit counters at once.

**This repository does not contain the naming engine.** The backend installs it from the `main`
branch of `Steinbeck-Lab/Orthonym` — see "The engine is not in this repo" below.

## Commands

```bash
# Redis first — everything below needs it, tests included.
docker compose up -d redis           # container orthonym-redis, localhost:6379

# tests — from the repo root; this script is the only correct way to run them
backend/scripts/run-tests.sh                              # full suite
backend/scripts/run-tests.sh tests/test_explain_tree.py -v  # one file

# backend — from backend/, three processes in three terminals
REDIS_URL=redis://localhost:6379/0 .venv/bin/python -m uvicorn app.main:app --port 8001
REDIS_URL=redis://localhost:6379/0 .venv/bin/python -m celery -A app.celery_app worker -Q fast  -c 2 -n fast@%h
REDIS_URL=redis://localhost:6379/0 .venv/bin/python -m celery -A app.celery_app worker -Q batch -c 2 -n batch@%h

# ad hoc scripts importing app.*
cd backend && PYTHONPATH="$(pwd)" REDIS_URL=redis://localhost:6379/0 .venv/bin/python <script.py>

# explain coverage census -- 665 names, prints the per-axis table. Runs the
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

The engine is installed from `github.com/Steinbeck-Lab/Orthonym@main`, never vendored:
`backend/requirements.txt` for a local venv, a BuildKit git source (`ADD ...Orthonym.git#${ORTHONYM_REF}`)
in `backend/Dockerfile`. The git source matters: BuildKit re-resolves `main` on every build and keys
the layer on the commit, where pip on a git URL would stay cached on the first commit it saw. A local
venv does not update on its own: `uv pip install --reinstall-package orthonym -r backend/requirements.txt`.
`--build-arg ORTHONYM_REF=<full 40-char SHA>` builds another commit; a short SHA fails to resolve.

Tracking `main` means an engine push can change a name or a tier with no commit here. The build's
SELF-01 check (`scripts/verify_opsin_live.py`, every Home example must keep its advertised tier) and
the backend CI job are what notice. A red one after an engine push is an engine change, not a bug here.

The engine fetches its own **OPSIN 2.9.0** and **centres 1.2.1** jars from their releases and
SHA-checks them (`orthonym/jars.py`), into `$ORTHONYM_JAR_DIR` (the image sets `/opt/orthonym/jars`)
or `~/.cache/orthonym/jars`. `orthonym --fetch-jars` is the loud version the Dockerfile and CI run. An
installed engine carries no OPSIN source tree, so app code never reads `PROJECT_ROOT/opsin/...`.

**CDK** is the app's own: `backend/Dockerfile` downloads it into `backend/vendor/cdk/` and checks it
against the SHA-256 in the tracked `backend/vendor/cdk/NOTICE`. `backend/.dockerignore` keeps
`backend/vendor/` out of the build context, so a build here exercises the same download path a fresh
clone does.

The name cache clears itself on an engine change: `app/name_cache.py` keys on a hash of the
installed engine's `.py` files. Bump `_KEY_VERSION` only when this app changes what a cached row means.

Without a live JVM and those jars, the Orthonym engine's SELF-01 self-consistency gate **fails
open**: a molecule that should report as a lower-confidence `fallback` ships as a `pin` nothing checked.
That is why `app/jvm_guard.py` refuses rather than degrades, and why the Dockerfile proves the gate
at build time.

## Gotchas

Things the repo does not tell you, or tells you only after they cost time.

**Environment**
- `REDIS_URL` defaults to `redis://redis:6379/0`, the compose hostname. Outside compose, set
  `redis://localhost:6379/0`.
- Port 8000 may be Orthonym's own compose backend or another project's container. Run a manual
  backend on 8001; `vite.config.js` proxies to 8000, so repoint it for a browser check and revert.
- Docker Desktop stops on its own. A 502 through the Vite proxy plus a `docker.sock` error means the
  daemon is down, not the code.

**Tests**
- Only `backend/scripts/run-tests.sh`. A bare `pytest` prints a correct summary and then hangs about
  10 minutes because JPype's JVM will not let the process exit. Script exit codes: 0 passed,
  1 failed, 2 no summary (a real hang).
- The suite needs Redis; `conftest.py` fails with instructions instead of skipping.
- Kill every Celery worker first: `pkill -9 -f "celery -A app.celery_app"`, and
  `docker stop orthonym-worker-fast orthonym-worker-batch` when compose is up, because `pkill` does
  not reach containers. A live worker consumes the jobs the tests submit and the concurrency-cap
  tests then fail on correct code.
- Tests share the Redis DB with manual runs and are not namespaced. Leftover keys fail
  `test_rate_limit.py` and `test_jobs_api.py` on unmodified code; check
  `docker exec orthonym-redis redis-cli --scan --pattern 'orthonym:*' | wc -l` and `FLUSHDB`
  before trusting a before/after.

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
  `/explain` use `.workspace`, `/about` uses `.about`, and the three legal pages use `.legal`. There
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
  change.
- **`tier` is the engine's, `status` is the app's claim.** Every name the engine emits has passed its
  own OPSIN round trip, unless OPSIN cannot read it at all; the tier says how it was built.
  `pin_verified` -> `pin`; `pin_unverified` and `systematic_verified` -> `fallback` (verified,
  preferred status not certified); `best_effort` -> `best_effort` (the engine's last-resort floor, or
  a name no round trip verified; since engine `eb25c33` a verified primary-pass name never gets it,
  so in practice it comes from the escalated pass, but best-effort mode off does not strictly rule
  it out). A missing
  round trip of the app's own demotes `status` to `best_effort` and never rewrites `tier`; the
  frontend reads that row (no `roundtrip_smiles`) as "Name not checked here", via
  `stateLabelFor` in `lib/statuses.js`. No label may call a name "unverified" beside a passing
  round trip (paper reviewer issue 2).
- The rendered chemical name is never uppercased or bolded; IUPAC case and weight are semantic.
- The rendered name IS typeset the way IUPAC prints it: italic stereodescriptors, element-symbol
  locants, `tert-`, indicated hydrogen and fusion letters; superscript bridge locants; subscript
  formula counts. `lib/nameTypography.js` decides which characters, `components/Typeset.jsx` renders
  them, and all seven name surfaces go through it. Display only — the string is never rewritten, and
  every copy/CSV/SDF path reads the data object, so the caret of `0^4,9` still leaves the page.
- `/from-name` computes no tier and no verdict: OPSIN either parses a name or does not, and borrowing
  Home's grammar there would claim a check that never ran.
- `/explain` explains **how the name is written**, from one OPSIN trace (`app/opsin_trace.py`): every
  written token is tagged with its text position right after OPSIN parses it; the trace keeps the
  candidate OPSIN itself returns (first one that builds without a warning) and checks it against
  OPSIN's public parse (`mismatch` refused). After `ComponentProcessor` every kept token records the
  part OPSIN placed it in (so a hydro prefix or ring bridge OPSIN moves into a ring lands on the
  ring), and `app/token_owner.py` assigns the tokens OPSIN used up by their written neighbours and
  brackets (a part OPSIN kept no token of, such as `spiro[...]`, adopts the used-up tokens inside its
  key range). `app/label_rules.py` is the token-kind table; `app/explain_tree.py` builds the flat
  `nodes` list. A stereo mark lights exactly one atom or none: the atom that carries its locant AND
  is a real stereocentre / stereo-double-bond atom (RDKit on the traced molecule), searched from its
  IUPAC scope; a bare R/S/E/Z lights the scope's main part's only stereocentre (or stereo double
  bond) when there is exactly one; a sugar's alpha/beta lights its one anomeric carbon, found by
  structure; D/L and bare cis/trans light nothing. A functional-class word ("ketone", "ether",
  "anhydride", "oxime", "chloride") is a part of its own over the atoms OPSIN's build adds for it
  (the trace takes them out of the alkyl written before it); a number beside an element symbol in
  front of a substituent ("4-O-") lights the PARENT's oxygen and carbon, never the substituent's own
  atoms. Suffix and parent lines state what the atoms are only when the atoms bear it out. Names
  OPSIN reads in a reordered form (CAS index names) are refused as `unplaced`. Known limitation:
  conjunctive names split the chain into the suffix. Honesty is **per node**: nothing lights a
  guessed atom, and on the SMILES path a part whose atoms cannot be agreed keeps its text with
  `atoms_unmapped`. Measured 2026-10-01 -- corpus 665 names: CLEAN 663, 2 OPSIN cannot read;
  ChEMBL 10k (run in 30 shards): CLEAN 9998, UNREADABLE 2, every failure class 0 (the census
  classes are listed in the header of `explain_census.py`). The gated sets are engine-named or
  curated, so a class they hold no name of is invisible to them: add the names to `CURATED` with
  the fix. Gate: `tests/test_explain_coverage.py`; census: `backend/scripts/explain_census.py`
  (`cd backend && ... scripts/explain_census.py --chembl tests/fixtures/explain_chembl_10k.tsv`).
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
