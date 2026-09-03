import { useEffect, useState } from 'react'

/**
 * Shown while an inline (fast-path) translate is in flight. That request blocks
 * for up to FAST_PATH_TIMEOUT (30s) and returns only when the whole batch is
 * named, so there is no per-molecule server progress to draw -- the honest
 * indicator is an INDETERMINATE bar (a stripe that keeps moving) plus a live
 * elapsed clock, which together read as "working", never "crashed". Once the
 * fast path times out the work becomes a real job and BatchResults takes over
 * with a true progress bar.
 */
export default function ProcessingBar({ count }) {
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    const start = performance.now()
    const id = setInterval(() => {
      setElapsed((performance.now() - start) / 1000)
    }, 100)
    return () => clearInterval(id)
  }, [])

  const molecules = count === 1 ? '1 molecule' : `${count} molecules`

  return (
    <section className="processing" role="status" aria-live="polite">
      <div className="processing__head">
        <span className="processing__label">Naming {molecules}</span>
        <span className="processing__elapsed">{elapsed.toFixed(1)}s</span>
      </div>
      <div className="processing__track" aria-hidden="true">
        <div className="processing__stripe" />
      </div>
      <p className="processing__note">
        Parsing each structure and checking every name back through OPSIN. A complex
        molecule can take a moment.
      </p>
    </section>
  )
}
