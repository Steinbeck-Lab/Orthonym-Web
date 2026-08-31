import { useCallback, useEffect, useState } from 'react'
import { checkHealth } from '../lib/api'
import './HealthCheck.css'

const STATE_LABEL = {
  checking: 'Checking…',
  healthy: 'Reachable & healthy',
  unreachable: 'Unreachable',
}

// Live status page for STITCH's backend. Mirrors the same three-phase
// grammar the Home register entries already use (queued/resolving/settled),
// so "healthy" reads as a stamped, double-ruled citation (the PIN device)
// and "unreachable" reads as a struck, redacted line (the error device) —
// no new semantic color is introduced for "healthy".
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
        setPhase('healthy')
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
  const rawDisplay = isChecking ? '—' : phase === 'healthy' ? JSON.stringify(raw) : error

  return (
    <>
      <div className="page-head page-shell">
        <h1 className="page-head__title">Is the engine up?</h1>
        <p className="page-head__lede">
          STITCH&rsquo;s naming engine runs behind a small backend API. This checks whether that
          backend is reachable right now &mdash; the same <code>GET /api/health</code> call the
          app itself relies on.
        </p>
      </div>

      <div
        className={`health-patch health-patch--${phase}`}
        role="status"
        aria-live="polite"
        aria-busy={isChecking}
      >
        <div className="health-patch__state">
        <div className="health-patch__top">
          <span className="health-patch__label">{STATE_LABEL[phase]}</span>
          <button
            type="button"
            className="btn"
            onClick={runCheck}
            disabled={isChecking}
          >
            {isChecking ? 'Checking…' : 'Check again'}
          </button>
        </div>

        <div className="health-patch__swatch" aria-hidden="true">
          {phase === 'checking' && (
            <div className="health-patch__pending-cloth">
              <span className="health-patch__pending-dash" />
              <span className="health-patch__pending-dash" />
              <span className="health-patch__pending-dash" />
            </div>
          )}
          {phase === 'healthy' && <div className="health-patch__fill" />}
          {phase === 'unreachable' && (
            <div className="health-patch__snip-wrap">
              <span className="health-patch__snip health-patch__snip--a" />
              <span className="health-patch__snip health-patch__snip--b" />
            </div>
          )}
        </div>
        </div>

        <dl className="health-patch__details">
          <div className="health-patch__row">
            <dt>Endpoint</dt>
            <dd>
              <code>GET /api/health</code>
            </dd>
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
    </>
  )
}

export default HealthCheck
