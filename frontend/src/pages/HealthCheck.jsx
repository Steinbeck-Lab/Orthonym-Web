import { useCallback, useEffect, useState } from 'react'
import { checkHealth } from '../lib/api'
import './HealthCheck.css'
import Icon from '../components/Icon'

// Four phases, not three. `degraded` is the one that was missing, and its
// absence was a lie the page told out loud: GET /api/health answers 200 with
// {"status":"DEGRADED","opsin":"no worker has a live JVM"} whenever no worker
// can verify a name, and this page rendered that as "Reachable & healthy"
// under the solid ink rule -- its single strongest positive signal -- because
// it branched on whether the FETCH resolved and never read the payload.
// Measured live, not theorised. PRODUCT.md principle 1 says determinism must
// be provable rather than asserted; a status page that asserts health it did
// not check is the same failure in a smaller frame.
const STATE_LABEL = {
  checking: 'Checking…',
  healthy: 'Reachable & healthy',
  degraded: 'Reachable, but degraded',
  unreachable: 'Unreachable',
}

// Live status page for STITCH's backend.
//
// The mark grammar is deliberate: checking = three shimmering hairline
// dashes, reachable = ONE solid 2px ink rule, degraded = that same rule at a
// shorter measure, unreachable = the struck pair. Reachable is deliberately
// NOT the double rule — paired ink lines already mean something else in this
// system (DESIGN.md's Don't list), and a state signal that borrows another
// state's shape carries no information at all. No hue is ever used for
// health.
//
// 2026-09-02: brought into Home's language. The opening is no longer a white
// `.page-head` card but `.page-hero` on the bare gradient ground, and the two
// cells are now the shared `.workspace` primitive rather than a private grid
// that redeclared the same 4fr/8fr split. Nothing about what the marks MEAN
// moved; only where they sit.
function HealthCheck() {
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
  const rawDisplay = isChecking ? '—' : raw !== null ? JSON.stringify(raw) : error

  return (
    <>
      {/* The opening is NOT a card. `.page-hero` (App.css) is the shared form
          of Home's `.home-hero`: no fill, no border, no shadow, no radius, so
          the page starts on the grey ground under the header notch instead of
          stacking a second white rectangle there. It self-insets, so it takes
          no `page-shell`.
          The lede is one sentence. The clause that used to finish it — that
          this is the same call the app itself relies on — moved down to sit
          beside the endpoint it is talking about, which is the only place a
          reader can check it. */}
      <section className="page-hero" aria-label="Introduction">
        <h1 className="page-hero__title">Is the engine up?</h1>
        <p className="page-hero__lede">
          STITCH&rsquo;s naming engine runs behind a small backend API &mdash; this asks whether
          it is reachable right now.
        </p>
      </section>

      {/* The live region stays exactly where it was: wrapped around BOTH
          cards, so a screen reader still gets the state word, the raw
          response and the timestamp on every check. It is a plain div and not
          a <main> on purpose — `role="status"` would overwrite the landmark,
          and moving the region down onto the state card alone would silently
          stop announcing the evidence that justifies it. */}
      <div
        className="workspace health-patch"
        role="status"
        aria-live="polite"
        aria-busy={isChecking}
      >
        <div className="health-patch__state">
          <span className="card__label">Backend status</span>

          {/* The state word, then its mark directly beneath it at a constant
              measure — the site's own "rule under the name" grammar, borrowed
              for a state that is not a confidence tier. */}
          <p className="health-patch__label">{STATE_LABEL[phase]}</p>

          {phase === 'degraded' && raw?.opsin && (
            <p className="prose-sm health-patch__reason">
              {raw.opsin}. Naming endpoints answer 503 until a worker reports one.
            </p>
          )}

          <div className="health-patch__swatch" aria-hidden="true">
            {phase === 'checking' && (
              <div className="health-patch__pending-cloth">
                <span className="health-patch__pending-dash" />
                <span className="health-patch__pending-dash" />
                <span className="health-patch__pending-dash" />
              </div>
            )}
            {phase === 'healthy' && <div className="health-patch__fill" />}
            {/* Degraded reuses the reachable rule at a SHORTER measure rather
                than borrowing a mark that already means something else. The
                connection really is there, so the line is really there; it
                just does not reach the end. No second vocabulary, and still
                nothing that could be mistaken for the double rule. */}
            {phase === 'degraded' && (
              <div className="health-patch__fill health-patch__fill--partial" />
            )}
            {phase === 'unreachable' && (
              <div className="health-patch__snip-wrap">
                <span className="health-patch__snip" />
                <span className="health-patch__snip" />
              </div>
            )}
          </div>

          {/* This surface's one primary action, so it is the one filled
              crimson glass button on the page. */}
          <div className="health-patch__actions">
            <button
              type="button"
              className="btn btn--accent"
              onClick={runCheck}
              disabled={isChecking}
            >
              <Icon name="refresh" />
              {isChecking ? 'Checking…' : 'Check again'}
            </button>
          </div>
        </div>

        <div className="health-patch__details">
          <span className="card__label">Evidence</span>

          <dl className="health-patch__list">
            <div className="health-patch__row">
              <dt>Endpoint</dt>
              <dd>
                <code>GET /api/health</code>
              </dd>
              <dd className="health-patch__hint">The same call the app itself relies on.</dd>
            </div>
            <div className="health-patch__row">
              <dt>Raw response</dt>
              <dd>
                <code className="health-patch__raw">{rawDisplay}</code>
              </dd>
            </div>
            <div className="health-patch__row">
              <dt>Checked at</dt>
              <dd>{checkedAt ? checkedAt.toLocaleString() : '—'}</dd>
            </div>
          </dl>
        </div>
      </div>
    </>
  )
}

export default HealthCheck
