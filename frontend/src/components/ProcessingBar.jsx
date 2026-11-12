import { useEffect, useState } from 'react'

/**
 * Shown while an inline (fast-path) translate is in flight. That request blocks
 * for up to FAST_PATH_TIMEOUT (30s) and returns only when the whole batch is
 * named, so there is no per-molecule server progress to draw -- the honest
 * indicator is an INDETERMINATE bar (a stripe that keeps moving) plus a live
 * elapsed clock, which together read as "working", never "crashed". Once the
 * fast path times out the work becomes a real job and BatchResults takes over
 * with a true progress bar.
 *
 * Not a live region: the clock changes ten times a second, and the page
 * announces the start and the outcome once each in its own status line.
 *
 * @param count   molecules being named, or null when not known yet (a file
 *                whose preview has not answered).
 * @param verify  OPSIN verify was on for this submission; off, no name is
 *                checked back, and the note must not say one is.
 */
export default function ProcessingBar({ count = null, verify = true }) {
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    const start = performance.now()
    const id = setInterval(() => {
      setElapsed((performance.now() - start) / 1000)
    }, 100)
    return () => clearInterval(id)
  }, [])

  const molecules = !Number.isFinite(count)
    ? 'your molecules'
    : count === 1
      ? '1 molecule'
      : `${count} molecules`

  return (
    <section className="processing" aria-busy="true">
      <div className="processing__head">
        <span className="processing__label">Naming {molecules}</span>
        <span className="processing__elapsed" aria-hidden="true">
          {elapsed.toFixed(1)}s
        </span>
      </div>
      <div className="processing__track" aria-hidden="true">
        <div className="processing__stripe" />
      </div>
      <p className="processing__note">
        {verify
          ? 'Parsing each structure and checking every name back through OPSIN.'
          : 'Parsing each structure. OPSIN verify is off, so no name is checked back.'}{' '}
        A complex molecule can take a moment.
      </p>
    </section>
  )
}
