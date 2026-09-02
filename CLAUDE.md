# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

STITCH is a public showcase web app for **OpenSTOUT** (private upstream `github.com/Kohulan/OpenSTOUT`;
`scripts/vendor-openstout.sh` takes `OPENSTOUT_SRC`. **Clone it fresh rather than pointing at a local
checkout** — see the refresh warning below), a deterministic,
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
docker compose up -d redis           # container stitch-redis, localhost:6379, volatile-lru

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
- **Kill every Celery worker before running the suite.** A worker left listening on the same
  Redis CONSUMES the jobs the tests submit, which silently breaks the tests that
  turn eager mode off on purpose — the concurrent cap reads as broken (10 admitted against a cap
  of 2) on correct code. `pkill -9 -f "celery -A app.celery_app"`, then confirm with `pgrep -fl`.
  **`pkill` does not reach a worker in a container**, and the compose stack publishes its Redis on
  the same `localhost:6379` the suite uses — so if `docker compose up` is running, also
  `docker stop stitch-worker-fast stitch-worker-batch` (check with `docker ps`).
- **The suite needs Redis running** (`docker compose up -d redis`, which is what `conftest.py`
  prints). There is no `stitch-redis-dev` container any more; the compose service is
  `stitch-redis`. `conftest.py` deliberately `pytest.fail`s with instructions rather than
  skipping when Redis is missing.
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
`openstout` from `backend/vendor/openstout` (a snapshot), not from a live checkout — Docker
builds can't reach outside their build context, and this keeps the backend reproducible without
assuming the sibling repo exists on the build host (on this machine it does not; point
`OPENSTOUT_SRC` at a clone). Refresh the snapshot after upstream OpenSTOUT
changes with `./scripts/vendor-openstout.sh`, then re-check `backend/vendor/openstout/README.md`
for updated accuracy numbers before touching any copy that cites them (see below).

**Refreshing: clone fresh, and check the version before you vendor anything.** Verified 2026-09-02:
the snapshot is already byte-identical to upstream `main` at `52f7afe` (2026-08-31) — 253 files,
same tree digest, same README, pyproject, NOTICE, LICENSE and both jars (`opsin-cli-2.9.0`,
`centres-cli-1.5`) — and the installed copies in `backend/.venv-mac` and inside the running
`stitch-worker-*` containers match it too. **The local checkout on this machine is a trap**: it lives
at `/Volumes/Data_Drive/My_Projects/2026/OpenSTOUT/Project` (not `~/OpenSTOUT/Project`, which does not
exist), sits on `main` at 2026-05-19, carries uncommitted work, and reports `__version__ = "0.1.0"` —
vendoring from it would **downgrade** the engine from 1.0.0. `gh` is authenticated with `repo` scope,
so `gh repo clone Kohulan/OpenSTOUT <dir> -- --depth 1` is the reliable source.

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
`batch` queue so a long job cannot occupy the slot someone naming ethanol needs. **Home drives all of this
as of 2026-09-02** (it was API-only until then): the input card has **Paste | Upload file | Draw**
tabs (Draw embeds the same Ketcher iframe `/explain` uses, through the same `useKetcher` handshake,
with `.workbench--draw` flipping the split so the editor gets the wide cell),
pasting more than `FAST_PATH_MAX_MOLECULES` submits a job instead of refusing the eleventh line, a
file gets a `parse-preview` count first, and `components/BatchResults.jsx` shows progress, a paged
table, Stop, Delete and a per-row **Draw** (`/api/depict`, one molecule at a time — batch rows
carry no picture on purpose). The Upload tab is a **drop zone**, not a bare `Choose File` button:
the whole slot is the target, the native input stays in the markup (hidden, so the label, keyboard
and platform picker still work), and the SVG seam around it runs its dashes while a file is over it
and goes solid once one lands. A dropped file's extension is checked in the browser, because a drop
never passes through the picker's `accept`.

`lib/jobStore.js` keeps `job_id` + `owner_token` in **localStorage**,
because the token is issued once and a reload would otherwise lose the ability to stop a
10,000-molecule job. **It holds only jobs that might still need stopping**: `BatchResults` calls
`forgetJob` the moment a job goes terminal, which is what makes a reload CLEAR the page. Keeping a
finished job (v1's behaviour) restored the batch panel on every load and survived a hard reload —
which cannot clear localStorage — so the panel could not be dismissed at all. The key is
`stitch.jobs.v2` and the bump is part of that fix: it retires every v1 entry rather than restoring
one last stale panel. Entries prune at `expires_at`, or at `rememberedAt + 24 h` when the first
status poll never landed and there is no `expires_at` to check.

Three things about that UI were **measured against the running backend**, not assumed, and each
would be easy to "simplify" back into a lie:
- **A cancelled job's rows do not exist immediately.** For as long as its in-flight chunks take to
  finish, `/results` answers `retrievable: 0` and `results.csv` answers **409**. Two measured
  cancels took over 13 s to produce 125 and 100 rows. So the panel waits (20 × 3 s), never offers
  the CSV link in that window, and when the wait is spent it says "no rows have appeared yet" with
  a **Check again** — it cannot know the job is empty.
- **`formula` is only ever set on an abstain** (`openstout_service.py`), so it rides inside the
  name cell rather than in a column that would be blank on every named row.
- **Every row carries its confidence rule** (double / dashed / dotted / faint / struck), because a
  table is exactly where PRODUCT.md principle 3 would be tempting to reduce to a word in a column.

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
(`NAME_CACHE_TTL_SECONDS`, 7 days) and the per-IP rate-limit counters. **The name cache now
invalidates itself on a vendor refresh** — `name_cache._engine_fingerprint()` hashes the OpenSTOUT
source actually installed in the process (40 ms over 253 files, paid once at import) into the key,
because upstream develops on a static version `1.0.0` and `_ENGINE_VERSION` therefore cannot
notice a refresh. `_KEY_VERSION` survives as a manual belt for the fallback case (a zipimport or
stripped image where the source cannot be read); bumping it by hand is no longer the only thing
standing between a vendor refresh and a stale name.

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

**Frontend routes share components deliberately, not by accident.** There are five routes, not
seven: `/structure` and `/teach` are `<Navigate>` redirects to `/explain?input=draw`, because both
were the same capability reached a different way. `/explain` now carries the input choice itself —
**IUPAC name | SMILES | Draw** tabs in the input card — plus a **Learn/Expert** switch in the
output card, Expert by default (PRODUCT.md principle 1: a proof you must hunt for a switch to see
is not offered). Learn drops the SMILES tab entirely rather than mislabel it, per the teach-mode
spec's rule against naming a format. Home (`/`, "Translate") renders results through
`SamplerGrid`/`Tile`. Four
routes open with the same `.page-head` card (a wide title+lede card); **Home does not** — since
2026-09-02 it opens with `.home-hero`, which is deliberately **not a card** (no fill, border,
shadow — or `isolation`; the owner asked for no white background there): the wordmark on the bare
grey ground **lit by a real WebGPU flare** (`frontend/src/lib/flare/`, vendored from vgpu's
`nextjs-flare` example, vercel-labs/vgpu, MIT — a 48-step ray walk in WGSL that rakes light along
the letter outlines, with the live `<h1>` as its light source and the frame inverted into a crimson
veil composited `multiply`, because light-on-light is invisible on grey). It is a dynamic import
(180 kB chunk) behind `'gpu' in navigator` and `prefers-reduced-motion`; without those, no canvas
mounts and the wordmark keeps a CSS halo. **Read DESIGN.md's `.home-hero` entry before touching
it** — four of its choices are departures from upstream that look arbitrary and are not. Plus a
tagline whose bold letters spell STITCH, and its old title+lede card and its accuracy band were both removed at
the owner's request. Every route closes on the same footer.
The working part of each route is a **contained** `.workspace` card grid (two rounded cards, input
| output, inside the `--shell-max` column — Home's is named `.workbench`; `/explain` adds
`.workspace--draw` **on the Draw tab only**, which flips the split so the structure editor takes the wide cell — Ketcher is unusable in the narrow column). `useKetcher` takes an `enabled` flag for the same reason: its 20 s readiness clock must start when the iframe mounts, not when the page does, or picking Draw late finds the editor already declared broken. There is
one `.workspace` definition in `App.css` — if you ever see two, the later one is a stale leftover
and wins the cascade; delete it. `Explain.jsx` and `Teach.jsx` no longer carry independent copies of
anything — a claim that was written one commit early and is now true: they shared **113
byte-identical lines** of SVG-injection and atom-highlight effects until those moved to
`frontend/src/lib/useAtomHighlight.js`, whose pure half (`highlightTargets`, `shouldHighlight`) is
the tested part. Both also import `sanitizeSvg`/`atomRefsOf`/`ATOM_REF_RE` from
`frontend/src/lib/svgHighlight.js` and share `frontend/src/lib/useKetcher.js`'s Ketcher
iframe-readiness handshake — which **Home's Draw tab now uses too**, along with the shared
`.structure-editor` iframe frame in `App.css` (it was `.explain__editor`, promoted when Home
gained a second embed of the same editor). `sanitizeSvg`'s
DOMPurify config now lives in exactly one place, because two copies of a sanitiser config is exactly
the kind of thing that drifts silently into an XSS hole.

**Read `DESIGN.md` before any visual change.** It's not aspirational — it documents the shipped
system as of 2026-08-26, a **TechX-style card bento** (dribbble shot 23855252, user-pinned "like
this") wearing **ChemAudit chrome**. The body is a **soft cool-grey ground** (`--ground: #d5d8dc`,
since 2026-09-02 a slow **gradient** ground — a fixed `.ground` layer of three blurred radial
fields, crimson at 6–9% plus one grey counterweight, drifting over 64–96s; **`.page` must stay
transparent and nothing may take a positive `z-index`**, or the layer is covered or the hero
flare's `multiply` breaks — see DESIGN.md)
carrying **rounded cards** (`--r-card: 22px`, inner tiles `--r-card-sm: 14px`) — white
(`--card`), quiet grey (`--card-soft`), and one or two **near-black feature cards** (`--card-dark`,
via the `.card--dark` primitive — as of 2026-09-02 **no surface uses one**, since Home's accuracy
band, which carried the only instance, was removed at the owner's request; the primitive stays in
the system) — separated by a modest `--gap: 14px`, in a **contained** column
(`--shell-max: 2200px`, not full-bleed — it was 1600, widened 2026-09-01). **Every card lifts** on a soft two-part `--card-shadow`;
a generic `.card` and `.bento` primitive live in `App.css`. Hairline seams survive only as
*internal* dividers inside a card (a tile's head/foot rule). Type is the three-face trinity —
**Saira Condensed** (display/wordmark/name), **Public Sans** (body), **JetBrains Mono**
(nav/labels/data) — at weight 400, with **three bold exceptions and no others**: Public Sans **700**
for the big stat figures (`.spec__value`, up to 2.75rem), the header's route labels, and the six
hero-tagline letters that spell STITCH (the last two by direct instruction, 2026-09-02). The
rendered chemical name stays 400 — IUPAC weight and case are semantic.
The **one crimson accent** (`--accent: #c41e3a`) is confined to chrome — active nav, the logo mark,
inline links, the focus ring, the one primary button per surface, the sliding active-route pill, the hero's flare
and the footer's self-sewing join — and **never touches a confidence tier or the round-trip
verdict**. The **header is one white notch island** cut into the top edge of the window (flush at
`top: 0`, 24px bottom corners, a concave CSS fillet on each flank, no shadow) and the **footer has
no band at all** (a transparent strip carrying two lifted pills). Both replaced ChemAudit's
floating glass on 2026-09-02 by instruction; the glass tokens now dress only the mobile menu
panel. Confidence stays a **monochrome rule beneath the name**
inside the white cards (double = PIN, dashed = fallback, dotted = best-effort, one faint rule =
abstain, two struck rules = error), at a constant `min(100%, 30ch)` — a measure that belongs to the
**mark** (drawn as an `::after`) and never to the name, which takes the full width of its card.
Two structural facts still
hold: every interactive page puts its input beside its own output (`.workspace`), and each page's
"how this works" copy lives on the About page.

**The one-screen shell only works because every cell clips.** `.page` is `100dvh; overflow: hidden`
and `.workbench` is the flexed row that gives — but with `overflow: visible` on its cells, content
taller than the row painted straight through the key band (121px) and the footer (71px), and a
batch table sharing the grid crushed the input card to 34px. `.workbench > * { min-height: 0;
overflow-y: auto }` is the fix: clipping is what makes a cell a scroll container, which is also
what lets an auto grid row shrink. Two related facts: `.batch` sits in the output column rather
than spanning both, and `.tile__depiction` has **no `aspect-ratio`** (a 4:3 box at card width was
650px tall and pushed the name out of view) — it takes the height the card has left, with a 180px
floor. Verify a layout change by MEASURING overlap in a browser, in the state that has results:
the one-screen commit checked only the empty state and shipped both collisions.

The world **began** pinned by the user to the "Bugatti design analysis" template
(getdesign.md/bugatti) and has since been steered, by successive user instructions, into a
**ChemAudit-chrome + TechX-card-bento** hybrid. Recorded departures from the Bugatti source —
each user-instructed or forced by product truth, do not "fix" them back: light inversion; substitute
open-source faces; a sans body (Public Sans) in place of the source's Garamond serif; WCAG 2.2 AA
contrast repairs; real hover states; the **ChemAudit chrome** (light-only, theme toggle dropped) —
whose floating-glass header and footer band were themselves replaced on 2026-09-02 by a notch
island and a bandless pill footer, also by instruction; the **one crimson chrome accent**; the **TechX card bento body** (grey
ground, rounded lifted cards, contained `--shell-max`, selective bold) that replaced the
flat 0-radius hairline-seam full-bleed body; and (load-bearing) **the chemical name is never
uppercased**, because IUPAC case is semantic. DESIGN.md records each with its reason. Two earlier worlds are **historical, not current**: the warm ecru/dot-grid "Citation" system
(Inter + Silkscreen, citation register, bracketed chips, citation-red margin rule) and the
"Source Serif 4 / codex paper / italic name" pass. If you find references to either anywhere
(comments, a stray screenshot filename), treat them as history.

`.impeccable/design.json` is DESIGN.md's machine-readable sidecar; keep both in sync if you change
a token. `.impeccable/review/*.png` are prior visual-audit screenshots — check the filename/mtime
against the current design system before trusting one as "what it looks like now."

**Accuracy claims cite a real, versioned benchmark — never round them up.** The three figures,
shown on **About** (Home's accuracy band was removed on the owner's instruction on 2026-09-02;
Home now links to About for it, and About states the version, the benchmark and the metric's own
definition, which is what PRODUCT.md principle 2 requires) — **94.8% round-trip exact match**, **0 wrong structures emitted**, over a
**1,500-molecule** ChEBI+PubChem set — are OpenSTOUT **v1.0.0**'s published numbers
(`backend/vendor/openstout/README.md` § Accuracy, which matches upstream). v1.0.0 publishes no per-corpus breakdown, so the
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
