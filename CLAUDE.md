# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

STITCH is a public showcase web app for **OpenSTOUT** (upstream at `~/OpenSTOUT/Project`, which is
**not present on every dev machine** — `scripts/vendor-openstout.sh` takes `OPENSTOUT_SRC`), a deterministic,
rule-based SMILES→IUPAC naming engine — as opposed to STOUT-V2, the neural model shown by the
separate sibling repo `~/STOUT_WebApp` (Vue 3 stack, unrelated codebase). **The two repos are easy
to confuse; a shell may open in `~/STOUT_WebApp` by mistake — `cd`/verify the path before editing.**

Stack: **React 19 + Vite** (frontend) / **FastAPI + Celery + Redis + RDKit + OpenSTOUT + OPSIN
(via JPype/a real JRE)** (backend). No database, no auth, no accounts — but the backend is **not a
single process any more**: naming runs in Celery workers, and Redis carries the broker, the job
results, the shared name cache and the per-IP rate-limit counters. See "The job layer" below.

## Commands

```bash
# Redis first — everything below needs it (tests included).
docker start stitch-redis-dev        # localhost:6379, maxmemory-policy volatile-lru

# tests — from the repo root. This script is the ONLY correct way to run them.
backend/scripts/run-tests.sh                            # full suite
backend/scripts/run-tests.sh tests/test_name_spans.py -v  # one file

# backend — from backend/. Three processes, not one: uvicorn alone answers
# /api/health with DEGRADED and 503s every naming endpoint, because no worker
# has recorded a live JVM. Each command wants its own terminal.
REDIS_URL=redis://localhost:6379/0 .venv-mac/bin/python -m uvicorn app.main:app --port 8001
REDIS_URL=redis://localhost:6379/0 .venv-mac/bin/python -m celery -A app.celery_app worker -Q fast  -c 2 -n fast@%h
REDIS_URL=redis://localhost:6379/0 .venv-mac/bin/python -m celery -A app.celery_app worker -Q batch -c 2 -n batch@%h

# ad hoc scripts importing app.*
cd backend && PYTHONPATH="$(pwd)" REDIS_URL=redis://localhost:6379/0 .venv-mac/bin/python <script.py>

# frontend — from frontend/
npm run dev      # vite dev server, proxies /api -> http://localhost:8000
npm run build
npm test         # node --test over src/**/*.test.js -- `node --test src/lib/` fails,
                 # it globs non-test files too; use the script
npx oxlint src/  # full-project `npm run lint` has pre-existing warnings in vendored public/standalone/ — out of scope

# whole stack
docker compose up -d --build
# -> frontend :8080, backend 127.0.0.1:8000, plus redis, worker-fast, worker-batch
```

**Gotchas that cost real time:**
- **`backend/.venv` is a Linux venv and cannot run here.** Its `pyvenv.cfg` records
  `/home/kohulan/STITCH/backend/.venv` and its `bin/python` is a dangling symlink to
  `/usr/bin/python3.12`. Use **`backend/.venv-mac/bin/python`** on macOS. This trap defeated three
  separate review agents; check the interpreter before you believe an import error.
- **Never run a bare `pytest`; run `backend/scripts/run-tests.sh`.** JPype's JVM refuses to let the
  process exit, so a bare `pytest` looks like a 10-minute hang ending in exit 144 *after* it has
  already printed a correct summary. The script waits for pytest's own summary line, kills the
  corpse, picks the right interpreter and points `REDIS_URL` at localhost. Its exit codes: `0` all
  passed, `1` tests failed, `2` no summary appeared (a real hang).
- **The suite needs Redis running** (`docker start stitch-redis-dev`). `conftest.py` deliberately
  `pytest.fail`s with instructions rather than skipping when it is missing.
- **`REDIS_URL` defaults to `redis://redis:6379/0`**, the compose-internal hostname. Anything run
  outside compose must override it to `redis://localhost:6379/0`.
- **Port 8000 is held by an unrelated project's container** (`bchemxtractweb-backend-1`), and it
  collides with STITCH's own `127.0.0.1:8000` compose binding — so `:8000` may be a different
  application's API entirely. Run a fresh backend on **8001** for manual testing; `vite.config.js`
  proxies `/api` to 8000, so temporarily repoint it at 8001 for a real browser check, then revert.
- **`.venv-mac` has no `pip`** — it was built with `uv venv --python 3.12`, so install into it with
  `uv pip install -r requirements.txt`, not `pip install`. It *does* have working console-script
  shims (`celery`, `pytest`, `uvicorn`, `openstout`, ...), each with a correct absolute shebang, so
  `.venv-mac/bin/celery --version` works; `.venv-mac/bin/python -m <tool>` is equally fine.
- **Playwright is reachable as an MCP server**, not a local install. `/home/kohulan/node_modules/playwright`
  does not exist on this machine.
- **`.env` and `.env.*` are unreadable** — a user-global deny rule in `~/.claude/settings.json`
  blocks them. Hand the text to the owner rather than narrowing the guard.

## Architecture

**The OpenSTOUT dependency is vendored, not live-pathed.** `backend/requirements.txt` installs
`openstout` from `backend/vendor/openstout` (a snapshot), not from `~/OpenSTOUT/Project` — Docker
builds can't reach outside their build context, and this keeps the backend reproducible without
assuming the sibling repo exists on the build host (on this machine it does not; point
`OPENSTOUT_SRC` at a clone). Refresh the snapshot after upstream OpenSTOUT
changes with `./scripts/vendor-openstout.sh`, then re-check `backend/vendor/openstout/README.md`
for updated accuracy numbers before touching any copy that cites them (see below).

**SELF-01 needs a real JVM, or it silently fails open.** OpenSTOUT's self-consistency gate (does a
candidate name round-trip back through OPSIN to the same structure?) requires JPype + a real JRE +
two vendored jars (OPSIN, `centres`). Without them, a name that should downgrade to `fallback` can
ship mislabeled as a verified `pin` — confirmed by direct testing, not theoretical. This is why the
Dockerfile installs `default-jre-headless` and why `backend/scripts/place_opsin_resources.py` runs
on every build/`pip install`. Don't strip either "to slim the image" without re-running the
regression check in `README.md` first (a fused polycyclic SMILES must come back `"fallback"`,
never `"pin"`).

**The job layer: naming happens in workers, and the web process refuses when they are missing.**
`POST /api/translate` still answers inline for **10 molecules or fewer** — it dispatches
`translate_fast` to the `fast` queue and blocks for up to `FAST_PATH_TIMEOUT` (30 s). Above that
limit, or when the fast path times out, it returns a `JobEnvelope` (`job_id`, `molecule_count`,
`status`) and the caller polls `GET /api/jobs/{id}` and `.../results`, or streams
`.../results.csv`. `POST .../cancel` stops a running job and `DELETE` discards a finished one;
both require the `owner_token` the JobEnvelope returned once, since a shared results URL carries
the id but not the token. Cancellation is cooperative — `redis_store.begin_chunk` already refuses
a terminal job, so writing status `cancelled` is the entire mechanism and no task ids are tracked. `POST /api/jobs` takes an uploaded `.sdf` / `.mol` / `.csv` (needs a `smiles`
column) / plain SMILES list, up to `MAX_BATCH_SIZE` (10,000) molecules and `MAX_FILE_SIZE_MB`
(50 MB); `frontend/nginx.conf` sets `client_max_body_size 210m`, and its default of 1 MB would
otherwise silently cap the advertised limit. Work is chunked (`BATCH_CHUNK_SIZE`, 25) onto the
`batch` queue so a long job cannot occupy the slot someone naming ethanol needs. **There is no
frontend UI for this yet** — the whole job layer is API-only, and batch upload on Home is scoped
but unstarted.

Two consequences that bite immediately:

- **`jvm_guard.require_a_live_jvm()` 503s every naming endpoint when no worker has a live JVM**,
  including `POST /api/jobs`. That is deliberate — SELF-01 fails *open*, so dispatching work nobody
  can verify would ship a fallback labelled `pin`. It means **uvicorn on its own is not a working
  backend**: `/api/health` reports `DEGRADED` and naming returns 503 until a worker boots and writes
  its status. Workers refresh that status on a heartbeat; a stale entry is treated as "no JVM".
- **`backend/config/{small,medium,large}.yml` are deployment profiles**, selected by
  `DEPLOYMENT_PROFILE` (default `medium`). Precedence is environment variable > profile > code
  default, implemented explicitly in `core/config.py` because pydantic-settings' own order is the
  opposite. Profiles must live under `backend/` — the Docker build context is `./backend`, so a
  repo-root `config/` is unreachable.

**Redis is load-bearing in four separate roles**, and `docker-compose.yml` runs it with
`--maxmemory-policy volatile-lru`, *not* `allkeys-lru`: Celery broker messages carry no TTL, so
`allkeys-lru` would evict queued work and silently lose jobs. The four roles are the Celery broker,
job meta/chunks/rows (`JOB_RESULT_TTL_SECONDS`, 24 h), the shared name cache
(`NAME_CACHE_TTL_SECONDS`, 7 days) and the per-IP rate-limit counters. **`name_cache._KEY_VERSION`
must be bumped by hand on every `vendor-openstout.sh` refresh** — upstream OpenSTOUT develops on a
static version `1.0.0`, so the version-keyed cache invalidation cannot fire on its own and a stale
name would survive an engine change.

**Rate limiting exists and is per-IP** (`ratelimit.py`): 60/min for the naming endpoints, 300/min
for job polling, 1200/min for `/api/depict`, plus 2 concurrent jobs and 20 jobs/hour per IP. The
backend's `127.0.0.1:8000` binding and `TRUST_PROXY_HEADERS=true` are a **pair, and neither is safe
alone** — published on `0.0.0.0` while trusting the header, an attacker sets a fresh `X-Real-IP` per
request and every cap is void; with the header untrusted behind nginx, the whole internet shares one
bucket and a single script 429s the site. Read the comment block in `docker-compose.yml` before
changing either.

**Confidence tiers are the product's whole point, not an implementation detail.** Every naming
result is one of: verified **PIN** → verified **fallback** (general engine, OPSIN round-trip
confirmed) → **best-effort** (a real name, but OPSIN-unverified) → honest **abstain**. These tiers
must never be visually or textually conflated — see DESIGN.md's border/texture grammar, which
encodes exactly this state machine and nothing else. `openstout_service.py` implements the
escalation between tiers; `explain.py` / `opsin_decompose.py` / `name_spans.py` implement the
`/explain` and `/teach` per-substituent breakdown (reflecting into OPSIN's package-private parse
tree — `opsin_decompose.self_check()` verifies this still works, since it's inherently
version-fragile). **That check now runs in the Celery worker, not the web process**: `main.py` no
longer imports `opsin_decompose`, and `celery_app.py` calls `self_check()` when each forked child
starts its JVM. A web process on its own never runs it.

**Frontend routes share components deliberately, not by accident.** Home (`/`, "Translate") and
Structure→IUPAC render results through the literal same `SamplerGrid`/`Tile` components. Every
route opens with the same `.page-head` card (a wide title+lede card) and closes on the same footer;
the working part of each route is a **contained** `.workspace` card grid (two rounded cards, input
| output, inside the 1600px column — Home's is named `.workbench`; Structure→IUPAC and Learn add
`.workspace--draw`, which flips the split so the structure editor takes the wide cell). There is
one `.workspace` definition in `App.css` — if you ever see two, the later one is a stale leftover
and wins the cascade; delete it. `Explain.jsx` and `Teach.jsx` no longer carry independent copies of
anything: both import `sanitizeSvg`/`atomRefsOf`/`ATOM_REF_RE` from `frontend/src/lib/svgHighlight.js`
and both share `frontend/src/lib/useKetcher.js`'s Ketcher iframe-readiness handshake. `sanitizeSvg`'s
DOMPurify config now lives in exactly one place, because two copies of a sanitiser config is exactly
the kind of thing that drifts silently into an XSS hole.

**Read `DESIGN.md` before any visual change.** It's not aspirational — it documents the shipped
system as of 2026-08-26, a **TechX-style card bento** (dribbble shot 23855252, user-pinned "like
this") wearing **ChemAudit chrome**. The body is a **soft cool-grey ground** (`--ground: #d5d8dc`)
carrying **rounded cards** (`--r-card: 22px`, inner tiles `--r-card-sm: 14px`) — white
(`--card`), quiet grey (`--card-soft`), and one or two **near-black feature cards** (`--card-dark`,
e.g. the 94.8% figure) — separated by a modest `--gap: 14px`, in a **contained** column
(`--shell-max: 1600px`, not full-bleed). **Every card lifts** on a soft two-part `--card-shadow`;
a generic `.card` and `.bento` primitive live in `App.css`. Hairline seams survive only as
*internal* dividers inside a card (a tile's head/foot rule). Type is the three-face trinity —
**Saira Condensed** (display/wordmark/name), **Public Sans** (body), **JetBrains Mono**
(nav/labels/data) — at weight 400, with **one selective-bold step**: Public Sans **700** for the big
stat figures only (`.spec__value`, up to 2.75rem); the rendered chemical name stays 400.
The **one crimson accent** (`--accent: #c41e3a`) is confined to chrome — active nav, the logo mark,
inline links, the focus ring, the one primary button per surface, a faint footer keyline — and
**never touches a confidence tier or the round-trip verdict**. The **header/footer are floating
16px-radius glass** (their own soft shadow). Confidence stays a **monochrome rule beneath the name**
inside the white cards (double = PIN, dashed = fallback, dotted = best-effort, one faint rule =
abstain, two struck rules = error), at a constant `min(100%, 30ch)`. Two structural facts still
hold: every interactive page puts its input beside its own output (`.workspace`), and each page's
"how this works" copy lives on the About page.

The world **began** pinned by the user to the "Bugatti design analysis" template
(getdesign.md/bugatti) and has since been steered, by successive user instructions, into a
**ChemAudit-chrome + TechX-card-bento** hybrid. Recorded departures from the Bugatti source —
each user-instructed or forced by product truth, do not "fix" them back: light inversion; substitute
open-source faces; a sans body (Public Sans) in place of the source's Garamond serif; WCAG 2.2 AA
contrast repairs; real hover states; the **ChemAudit floating-glass header/footer** (light-only,
theme toggle dropped); the **one crimson chrome accent**; the **TechX card bento body** (grey
ground, rounded lifted cards, contained 1600px, selective bold for stat figures) that replaced the
flat 0-radius hairline-seam full-bleed body; and (load-bearing) **the chemical name is never
uppercased**, because IUPAC case is semantic. DESIGN.md records each with its reason. Two earlier worlds are **historical, not current**: the warm ecru/dot-grid "Citation" system
(Inter + Silkscreen, citation register, bracketed chips, citation-red margin rule) and the
"Source Serif 4 / codex paper / italic name" pass. If you find references to either anywhere
(comments, a stray screenshot filename), treat them as history.

`.impeccable/design.json` is DESIGN.md's machine-readable sidecar; keep both in sync if you change
a token. `.impeccable/review/*.png` are prior visual-audit screenshots — check the filename/mtime
against the current design system before trusting one as "what it looks like now."

**Accuracy claims cite a real, versioned benchmark — never round them up.** The three figures
shown on Home and About — **94.8% round-trip exact match**, **0 wrong structures emitted**, over a
**1,500-molecule** ChEBI+PubChem set — are OpenSTOUT **v1.0.0**'s published numbers
(`~/OpenSTOUT/Project/README.md` § Accuracy). v1.0.0 publishes no per-corpus breakdown, so the
site shows none; the earlier four-figure v21.0 split (~30.4% / 29.6% / 16.9% / 92.2%, 7,500
compounds) is **superseded and must not be restored**.
When OpenSTOUT ships a new milestone, verify the vendored snapshot and the frontend copy in
`Home.jsx`/`About.jsx` all cite the same version before changing any number.

## Product principles (from `PRODUCT.md`, load-bearing for any UX decision)

1. Determinism must be provable, not asserted — hence the visible OPSIN round-trip line on every
   named tile.
2. Never overstate measured accuracy; cite the version and benchmark, and state the metric's own definition (a refusal counts as a failure). The accuracy band is load-bearing, not fine print.
3. PIN-vs-fallback-vs-best-effort status must be visible wherever a name appears, never a footnote.
4. Image→SMILES (DECIMER/OCSR) is the one permanent exclusion — everything else from STOUT_WebApp
   is fair game to borrow as a UX reference, but STITCH has its own separate codebase and identity.
