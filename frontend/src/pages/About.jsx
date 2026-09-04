import { useCallback, useEffect, useState } from 'react'
import { checkHealth } from '../lib/api'
import Icon from '../components/Icon'
import './About.css'

// Four phases, not three. `degraded` is the one that was missing when this
// board was still its own /health page, and its absence was a lie the page
// told out loud: GET /api/health answers 200 with
// {"status":"DEGRADED","opsin":"no worker has a live JVM"} whenever no worker
// can verify a name, and the old page rendered that as "Reachable & healthy"
// under its single strongest positive mark, because it branched on whether
// the FETCH resolved and never read the payload. Measured live, not
// theorised. PRODUCT.md principle 1 says determinism must be provable rather
// than asserted; a status board that asserts health it did not check is the
// same failure in a smaller frame. Folded into About on 2026-09-04 (Task 18,
// owner instruction: "move the health check to about and keep it as a
// message board rather than a whole page") — the fix below is the thing that
// had to survive the move, not merely the feature.
const STATE_LABEL = {
  checking: 'Checking…',
  healthy: 'Reachable & healthy',
  degraded: 'Reachable, but degraded',
  unreachable: 'Unreachable',
}

// The mark grammar is deliberate and carried over byte-for-byte from the old
// page: checking = three shimmering hairline dashes, reachable = ONE solid
// 2px ink rule, degraded = that same rule at a shorter measure, unreachable =
// the struck pair. Reachable is deliberately NOT the double rule -- paired
// ink lines already mean a verified PIN elsewhere in this system (DESIGN.md's
// Don't list), and a state signal that borrows another state's shape carries
// no information at all. No hue is ever used for health. The board only
// scales the marks down for a compact strip; it does not substitute a shape.
//
// Scope, by the owner's own instruction when asked how much of the old page
// should survive: "status line + details" -- the state mark and sentence, a
// Check again button, and the raw /api/health payload behind a small
// <details> toggle. The endpoint name and the "same call the app itself
// relies on" aside did not make the cut; the payload speaks for itself here.
function ServiceStatus() {
  const [phase, setPhase] = useState('checking')
  const [raw, setRaw] = useState(null)
  const [error, setError] = useState(null)
  const [checkedAt, setCheckedAt] = useState(null)

  const runCheck = useCallback(() => {
    setPhase('checking')
    checkHealth()
      .then((data) => {
        setRaw(data)
        setError(null)
        setCheckedAt(new Date())
        // Read the payload, not merely the fact that one arrived. Anything
        // other than "OK" is degraded: an unrecognised status is reported as
        // less-than-healthy rather than as healthy, which is the fail-closed
        // direction for a claim about health.
        setPhase(data?.status === 'OK' ? 'healthy' : 'degraded')
      })
      .catch((err) => {
        setRaw(null)
        setError(err?.message || 'network error')
        setCheckedAt(new Date())
        setPhase('unreachable')
      })
  }, [])

  useEffect(() => {
    runCheck()
  }, [runCheck])

  const isChecking = phase === 'checking'
  const rawDisplay = isChecking ? '—' : raw !== null ? JSON.stringify(raw, null, 2) : error

  return (
    <section className="about-band" aria-label="Service status">
      <div className="about-band__title-row about-band__title-row--status">
        <h2>Service status</h2>
        {/* A utility action beside a heading, not this surface's one primary
            action -- so the plain frosted `.btn`, not `.btn--accent`, and
            `.btn--sm` per the owner's 2026-09-04 instruction to size utility
            controls down from the 44px touch target. */}
        <button type="button" className="btn btn--sm" onClick={runCheck} disabled={isChecking}>
          <Icon name="refresh" />
          {isChecking ? 'Checking…' : 'Check again'}
        </button>
      </div>

      <div
        className="status-board"
        role="status"
        aria-live="polite"
        aria-busy={isChecking}
      >
        <div className="status-board__row">
          <span className="status-board__mark" aria-hidden="true">
            {phase === 'checking' && (
              <span className="status-board__pending">
                <span className="status-board__pending-dash" />
                <span className="status-board__pending-dash" />
                <span className="status-board__pending-dash" />
              </span>
            )}
            {phase === 'healthy' && <span className="status-board__fill" />}
            {/* Degraded reuses the reachable rule at a SHORTER measure rather
                than borrowing a mark that already means something else (the
                dashed and dotted rules mean fallback and best-effort, which
                are claims about a NAME, not about a server). The connection
                really is there, so the line is really there; it just does
                not reach the end. */}
            {phase === 'degraded' && (
              <span className="status-board__fill status-board__fill--partial" />
            )}
            {phase === 'unreachable' && (
              <span className="status-board__snip-wrap">
                <span className="status-board__snip" />
                <span className="status-board__snip" />
              </span>
            )}
          </span>

          <div className="status-board__text">
            <p className="status-board__label">{STATE_LABEL[phase]}</p>
            {phase === 'degraded' && raw?.opsin && (
              <p className="prose-sm status-board__reason">
                {raw.opsin}. Naming endpoints answer 503 until a worker reports one.
              </p>
            )}
            <p className="status-board__meta">
              {checkedAt ? `Checked ${checkedAt.toLocaleString()}` : '—'}
            </p>
          </div>
        </div>

        {/* A native <details>/<summary> disclosure: it needs no state and no
            ARIA of its own, which matches this codebase's preference for
            letting the platform do the work. Closed by default -- there is
            no `open` attribute. On `unreachable` this shows the error text
            where the payload would otherwise be (`rawDisplay` above already
            resolves to `error` in that case). */}
        <details className="status-board__details">
          <summary>Raw response</summary>
          <pre className="status-board__raw">{rawDisplay}</pre>
        </details>
      </div>
    </section>
  )
}

// About STITCH: what it is, how it works, its measured accuracy, and the
// verified facts (author, license, acknowledgments) behind the naming
// engine it showcases. Every claim here traces to the engine's own repo
// (pyproject.toml, LICENSE, README) or to this app's own shipped copy —
// nothing invented. The three figures in the spec band below are the same
// measured numbers the accuracy paragraph cites, not new claims. They come
// from OpenSTOUT v1.0.0's README; the earlier four-figure v21.0 split is
// gone because v1.0.0 publishes no per-corpus breakdown to cite.
//
// EXACTLY TWO top-level children: the hero, then the reading column.
// App.css's `.page__content > * + *:not(.site-footer)` is what supplies the
// 14px between them, so a third box here would add a stray gap and a single
// merged box would lose it.
function About() {
  return (
    <>
      {/* The opening is NOT a card. It was `.page-head` — a wide white
          rectangle stacked directly under the white header notch — until
          Home dropped that shape on 2026-09-02 for a wordmark sitting
          straight on the grey ground. `.page-hero` (App.css) is that same
          move for a route that has a title instead of a wordmark: no fill,
          no border, no shadow, no radius, and no stacking context, so the
          gradient ground shows through and the page begins with the floor.
          It self-insets to the shell column, so it must NOT also take
          `page-shell` — that would pad it twice. */}
      <section className="page-hero" aria-label="Introduction">
        <h1 className="page-hero__title">About Stitch</h1>
        {/* One sentence. The rest of the old lede — the acronym's expansion
            and the succeeds / falls back / declines clause — was not deleted,
            it moved down into "How it works", where the same three outcomes
            are already the subject. */}
        <p className="page-hero__lede">
          A public showcase for a deterministic, rule-based SMILES-to-IUPAC-name engine.
        </p>
      </section>

      <main className="about-page">
        {/* OpenSTOUT v1.0.0's published figures (its README § Accuracy),
            shown at full size rather than tucked into fine print. v1.0.0
            publishes no per-corpus breakdown, so none is shown. */}
        <section className="about-band" aria-label="Measured accuracy">
          <div className="spec">
            <div className="spec__cell">
              <span className="spec__value">94.8%</span>
              <span className="spec__label">Round-trip exact match</span>
            </div>
            <div className="spec__cell">
              <span className="spec__value">0</span>
              <span className="spec__label">Wrong structures emitted</span>
            </div>
            <div className="spec__cell">
              <span className="spec__value">1,500</span>
              <span className="spec__label">Molecules benchmarked</span>
            </div>
          </div>
          {/* PRODUCT.md principle 2: a figure travels with its version, its
              benchmark and its metric's own definition — never as a bare
              percentage. All three restate what the accuracy band below
              already says; nothing new is claimed here. A caption, not a
              paragraph, so the mono face is legal. */}
          <p className="about-spec-source">
            OpenSTOUT v1.0.0 &middot; 1,500 molecules from ChEBI and PubChem &middot; a refusal to
            name counts as a failure
          </p>
        </section>

        <section className="about-band about-band--split" aria-label="How accurate is it">
          <div className="about-band__head">
            <h2>How accurate is it?</h2>
          </div>
          <div className="about-band__body">
            <p className="prose">
              STITCH&rsquo;s naming engine is rule-based, so the same input always gives the same
              output, and it will tell you when it isn&rsquo;t sure.
            </p>
            <p className="prose">
              The headline metric is round-trip exact match: name the structure, parse the name
              back with OPSIN, and compare canonical identifiers, counting any refusal to name as
              a failure. It is reference-free &mdash; it does not depend on a possibly-noisy
              database name. On a 1,500-molecule benchmark drawn from ChEBI and PubChem,
              OpenSTOUT v1.0.0 scores 94.8% round-trip exact match and emitted 0 wrong
              structures.
            </p>
            <p className="prose">
              That second figure is the design priority: never emit a name for the wrong
              molecule. When a preferred name cannot be built with confidence, the engine drops
              to a less-preferred but still correct systematic name, or abstains &mdash; it does
              not guess. A lower-confidence name is always shown as such, never hidden.
            </p>
          </div>
        </section>

        <section className="about-band about-band--split" aria-label="How it works">
          <div className="about-band__head">
            <h2>How it works</h2>
          </div>
          <div className="about-band__body">
            {/* Moved down out of the old title card's lede, unchanged in
                substance: the acronym's expansion, and the three outcomes
                the paragraph after it then names one by one. */}
            <p className="prose">
              STITCH &mdash; SMILES To IUPAC name Translator for Chemistry &mdash; is built so
              visitors can try the engine on real molecules and see exactly how it behaves,
              including where it succeeds, where it falls back, and where it honestly declines to
              guess.
            </p>
            <p className="prose">
              Every SMILES string you submit goes through a fixed set of IUPAC nomenclature rules
              &mdash; there&rsquo;s no model and no training data involved, so the same input
              always produces the same output. Internally, the engine checks its own answer: it
              names the structure, then feeds that name into OPSIN, an independent
              name-to-structure parser, to see whether the round trip lands back on the same
              molecule. A name that round-trips cleanly under the engine&rsquo;s strict
              preferred-name rules is shown as a Preferred IUPAC Name (PIN). A name that
              round-trips but doesn&rsquo;t meet that strict standard is still shown, but labeled
              as a fallback rather than presented as equivalent to a PIN. When the engine
              isn&rsquo;t confident enough to produce a name at all, it abstains instead of
              guessing &mdash; and says so.
            </p>
          </div>
        </section>

        <section className="about-band about-band--split" aria-label="How each page works">
          <div className="about-band__head">
            <h2>How each page works</h2>
          </div>
          <div className="about-band__body">
            <div className="about-sub">
              <h3>Structure &rarr; IUPAC</h3>
              <p className="prose">
                Draw a molecule, then press Translate &mdash; the drawn structure is read straight
                out of the editor as a SMILES string and sent to the same engine behind the
                Translate page. The result lands in the same register entry you&rsquo;d see there:
                a double-ruled name means a confirmed Preferred IUPAC Name (PIN), a dashed
                underline is a lower-confidence but round-trip&ndash;verified fallback, a faint
                dotted underline means a name the engine could produce but not verify, and an
                empty ruled slot means it honestly couldn&rsquo;t name it at all.
              </p>
            </div>
            <div className="about-sub">
              <h3>IUPAC &rarr; Structure</h3>
              <p className="prose">
                This direction runs through OPSIN, not STITCH&rsquo;s own naming engine in
                reverse. STITCH&rsquo;s naming engine turns structures into names; going the other
                way needs a name-to-structure parser instead, so this page hands your text
                straight to OPSIN. If OPSIN can&rsquo;t resolve a name &mdash; a trade name, a
                misspelling, or anything outside strict IUPAC nomenclature &mdash; STITCH says so
                plainly rather than guessing.
              </p>
            </div>
            <div className="about-sub">
              <h3>Explain and Learn</h3>
              <p className="prose">
                Every highlight comes from OPSIN&rsquo;s own parse of the name, never a guess. The
                name is broken into the parts OPSIN itself found &mdash; the parent skeleton, each
                substituent, the ending that names the main group, and prefixes that only move
                hydrogens around &mdash; and each part carries the atoms OPSIN built it from.
                Failure is per part: anything STITCH can&rsquo;t pin to specific atoms is marked
                &ldquo;could not work out which atoms,&rdquo; and the parts around it are
                unaffected. Explain takes a typed SMILES or a typed name; Learn takes a drawn
                structure. Same breakdown, different way in.
              </p>
            </div>
          </div>
        </section>

        {/* At a glance — verified facts as a row of small cards on the grey
            ground, the same rounded-card vocabulary every other surface on
            the site uses. `role="list"` is not optional: index.css sets
            `list-style: none` globally, which strips the list semantics from
            a bare <ul> in Safari/VoiceOver. */}
        <section className="about-band" aria-label="At a glance">
          <div className="about-band__title-row">
            <h2>At a glance</h2>
          </div>
          <ul className="about-cards" role="list">
            <li className="about-card">
              <span className="about-card__label">Engine</span>
              <p className="about-card__body">
                Deterministic and rule-based &mdash; not a language model.
              </p>
            </li>
            <li className="about-card">
              <span className="about-card__label">Version</span>
              <p className="about-card__body">
                OpenSTOUT v1.0.0 &mdash; its first public release.
              </p>
            </li>
            <li className="about-card">
              <span className="about-card__label">License</span>
              <p className="about-card__body">MIT</p>
            </li>
            <li className="about-card">
              <span className="about-card__label">Author</span>
              <p className="about-card__body">Kohulan Rajan</p>
            </li>
          </ul>
          <div className="about-band__foot">
            <p className="prose-sm">
              STITCH&rsquo;s naming engine is open source, released under the MIT License.{' '}
              <a
                className="about-link"
                href="https://github.com/Kohulan/OpenSTOUT"
                target="_blank"
                rel="noopener noreferrer"
              >
                View the naming engine&rsquo;s source code
              </a>
              .
            </p>
          </div>
        </section>

        {/* The live board sits here rather than at the very top or bottom:
            after the static facts it is a sibling to ("At a glance" states
            what the engine IS; this states whether it is UP right now), and
            before "Acknowledgments" so the page still closes on credits to
            the other software it depends on, which reads as the natural
            last word on an About page. */}
        <ServiceStatus />

        <section className="about-band" aria-label="Acknowledgments">
          <div className="about-band__title-row">
            <h2>Acknowledgments</h2>
          </div>
          <ul className="about-cards" role="list">
            <li className="about-card">
              <span className="about-card__label">IUPAC Blue Book 2013</span>
              <p className="about-card__body">
                Source of the nomenclature rules the naming engine implements.
              </p>
            </li>
            <li className="about-card">
              <span className="about-card__label">OPSIN</span>
              <p className="about-card__body">
                Used for name-to-structure conversion, to validate names.
              </p>
            </li>
            <li className="about-card">
              <span className="about-card__label">RDKit</span>
              <p className="about-card__body">Used for molecular perception.</p>
            </li>
            <li className="about-card">
              <span className="about-card__label">ChEBI</span>
              <p className="about-card__body">Source of a validation dataset.</p>
            </li>
          </ul>
        </section>
      </main>
    </>
  )
}

export default About
