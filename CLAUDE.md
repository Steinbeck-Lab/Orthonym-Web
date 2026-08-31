# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Orthonym is a public showcase web app for **Orthonym** (`~/Orthonym/Project`), a deterministic,
rule-based SMILES→IUPAC naming engine — as opposed to STOUT-V2, the neural model shown by the
separate sibling repo `~/STOUT_WebApp` (Vue 3 stack, unrelated codebase).

Stack: **React 19 + Vite** (frontend) / **FastAPI + RDKit + Orthonym + OPSIN (via JPype/a real
JRE)** (backend). No database, no auth, no accounts.

## Commands

```bash
# backend — from backend/
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8001   # NOT 8000, see below
.venv/bin/python -m pytest                                             # full suite
.venv/bin/python -m pytest tests/test_name_spans.py -k some_test       # single test
PYTHONPATH=/home/kohulan/Orthonym-Web/backend .venv/bin/python <script.py>   # ad hoc scripts importing app.*

# frontend — from frontend/
npm run dev      # vite dev server, proxies /api -> http://localhost:8000
npm run build
npx oxlint src/  # full-project `npm run lint` has pre-existing warnings in vendored public/standalone/ — out of scope

# whole stack
docker compose up -d --build   # frontend :8080, backend :8000
```

**Gotchas that cost real time:**
- **Port 8000 is usually a stale Docker container** (`orthonym-backend`) that doesn't have your
  branch's changes. Run a fresh backend on **8001** for manual testing; `vite.config.js` proxies
  `/api` to 8000, so temporarily repoint it at 8001 for a real browser check, then revert.
- **pytest's own reported wall-clock/exit code lie.** The JVM (JPype, for OPSIN/centres) refuses
  to let the process exit after the suite actually finishes in ~4–5s, so you'll see 120+s and exit
  144 *after* the real (correct) summary line already printed. Redirect to a log file / run in the
  background and grep for `passed`; never trust the wall-clock or exit code alone.
- The backend venv has **no `pip`** and no console-script shims — always invoke
  `.venv/bin/python -m <tool>`, never a bare script name.
- Playwright (for manual UI verification) is available via `/home/kohulan/node_modules/playwright`,
  not a local install; Chromium is already cached there.

## Architecture

**The Orthonym dependency is vendored, not live-pathed.** `backend/requirements.txt` installs
`orthonym` from `backend/vendor/orthonym` (a snapshot), not from `~/Orthonym/Project` — Docker
builds can't reach outside their build context, and this keeps the backend reproducible without
assuming the sibling repo exists on the build host. Refresh the snapshot after upstream Orthonym
changes with `./scripts/vendor-orthonym.sh`, then re-check `backend/vendor/orthonym/README.md`
for updated accuracy numbers before touching any copy that cites them (see below).

**SELF-01 needs a real JVM, or it silently fails open.** Orthonym's self-consistency gate (does a
candidate name round-trip back through OPSIN to the same structure?) requires JPype + a real JRE +
two vendored jars (OPSIN, `centres`). Without them, a name that should downgrade to `fallback` can
ship mislabeled as a verified `pin` — confirmed by direct testing, not theoretical. This is why the
Dockerfile installs `default-jre-headless` and why `backend/scripts/place_opsin_resources.py` runs
on every build/`pip install`. Don't strip either "to slim the image" without re-running the
regression check in `README.md` first (a fused polycyclic SMILES must come back `"fallback"`,
never `"pin"`).

**Confidence tiers are the product's whole point, not an implementation detail.** Every naming
result is one of: verified **PIN** → verified **fallback** (general engine, OPSIN round-trip
confirmed) → **best-effort** (a real name, but OPSIN-unverified) → honest **abstain**. These tiers
must never be visually or textually conflated — see DESIGN.md's border/texture grammar, which
encodes exactly this state machine and nothing else. `orthonym_service.py` implements the
escalation between tiers; `explain.py` / `opsin_decompose.py` / `name_spans.py` implement the
`/explain` and `/teach` per-substituent breakdown (reflecting into OPSIN's package-private parse
tree — `opsin_decompose.self_check()` verifies this still works at every startup, since it's
inherently version-fragile).

**Frontend routes share components deliberately, not by accident.** Home (`/`, "Translate") and
Structure→IUPAC render results through the literal same `SamplerGrid`/`Tile` components. Every
route opens with the same `.page-head` card (a wide title+lede card) and closes on the same footer;
the working part of each route is a **contained** `.workspace` card grid (two rounded cards, input
| output, inside the 1600px column — Home's is named `.workbench`; Structure→IUPAC and Learn add
`.workspace--draw`, which flips the split so the structure editor takes the wide cell). There is
one `.workspace` definition in `App.css` — if you ever see two, the later one is a stale leftover
and wins the cascade; delete it. `Explain.jsx` and `Teach.jsx` independently duplicate `sanitizeSvg`/`atomRefsOf`/`ATOM_REF_RE`
(byte-identical, including the DOMPurify config) — extract to `frontend/src/lib/svgHighlight.js`
only when a third page needs the atom-glow, not before (see `NEXT-SESSION.md`'s "documented
follow-up" for the exact trigger condition).

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
**1,500-molecule** ChEBI+PubChem set — are Orthonym **v1.0.0**'s published numbers
(`~/Orthonym/Project/README.md` § Accuracy). v1.0.0 publishes no per-corpus breakdown, so the
site shows none; the earlier four-figure v21.0 split (~30.4% / 29.6% / 16.9% / 92.2%, 7,500
compounds) is **superseded and must not be restored**.
When Orthonym ships a new milestone, verify the vendored snapshot and the frontend copy in
`Home.jsx`/`About.jsx` all cite the same version before changing any number.

## Product principles (from `PRODUCT.md`, load-bearing for any UX decision)

1. Determinism must be provable, not asserted — hence the visible OPSIN round-trip line on every
   named tile.
2. Never overstate measured accuracy; cite the version and benchmark, and state the metric's own definition (a refusal counts as a failure). The accuracy band is load-bearing, not fine print.
3. PIN-vs-fallback-vs-best-effort status must be visible wherever a name appears, never a footnote.
4. Image→SMILES (DECIMER/OCSR) is the one permanent exclusion — everything else from STOUT_WebApp
   is fair game to borrow as a UX reference, but Orthonym has its own separate codebase and identity.
