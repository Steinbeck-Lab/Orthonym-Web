import { Fragment, useCallback, useEffect, useRef, useState } from 'react'
import {
  JobGoneError,
  cancelJob,
  deleteJob,
  depictMolecule,
  fetchJobResults,
  fetchJobStatus,
  jobResultsCsvUrl,
} from '../lib/api'
import {
  PAGE_SIZE,
  clampPage,
  expiryLabel,
  isTerminal,
  pageCount,
  progressPercent,
  stateLabel,
} from '../lib/batchJob'
import { forgetJob, rememberJob } from '../lib/jobStore'
import { STATE_CLASS, STATE_LABEL } from '../lib/statuses'

// One submitted batch: its progress while it runs, then its rows.
//
// Three shapes of honesty are load-bearing here, not decoration:
//
//   1. EVERY row carries its confidence mark. PRODUCT.md principle 3 -- the
//      tier must be visible wherever a name appears, never a footnote -- so
//      each name gets the same rule grammar the result tiles use (double =
//      verified PIN, dashed = verified fallback, dotted = unverified best
//      effort, faint = honest abstain, struck = error). A table is the one
//      place it would be tempting to reduce that to a word in a column.
//   2. The results link is NEVER presented as permanent. The backend keeps a
//      job for 24 hours and then deletes it; `expires_at` is shown in plain
//      words next to the download (design spec section 14, risk 2).
//   3. Structures are drawn ONE AT A TIME, on request. Batch rows deliberately
//      carry no depiction_svg -- an SVG per row would put tens of megabytes in
//      Redis for a 5,000-row job -- and /api/depict exists for exactly this.
//      Drawing a whole page automatically would fire 50 requests against a
//      budget the small deployment profile sets to 300 a minute.
//
// Polling: every 1.5s while the job is live, which is 40 requests a minute
// against a poll budget of 300 -- and it STOPS on a terminal status. It also
// stops when the tab is hidden, because a backgrounded tab polling a queue is
// pure waste.
const POLL_MS = 1500

// How long to keep asking for rows that are not there yet, after a job has
// gone terminal.
//
// Measured, twice, against the running backend: a cancelled job answers
// `retrievable: 0` for as long as its in-flight chunks take to finish -- the
// row list is assembled after that. One 400-molecule cancel took over 13
// seconds to produce its 125 rows, and a 300-molecule one produced 100 rows
// somewhere past the same mark. Both times the molecules were 150-carbon
// chains, which is about as slow as this engine gets.
//
// So: 20 tries at 3s, and when they are spent the UI offers to look again
// rather than declaring the job empty. It cannot know that it is empty --
// only that the rows have not appeared yet -- and saying otherwise is exactly
// the kind of confident falsehood this codebase is built to avoid.
const SETTLE_MS = 3000
const SETTLE_TRIES = 20

function rowKey(row) {
  return `${row.index}-${row.input}`
}

/** The confidence mark, in the same grammar the tiles use. */
function NameCell({ row }) {
  const stateClass = STATE_CLASS[row.status] ?? 'error'
  const label = STATE_LABEL[row.status]
  if (row.name) {
    return (
      <div className={`batch__name batch__name--${stateClass}`}>
        <span className="batch__name-text">{row.name}</span>
        <span className="sr-only">{label ? ` — ${label}` : ''}</span>
      </div>
    )
  }
  // No name: the abstain and error states still need their own mark, or a
  // reader cannot tell "the engine refused" from "the input was unreadable".
  //
  // The formula rides along HERE rather than in a column of its own, because
  // the engine only ever fills it for an abstain -- it is the consolation for
  // a molecule it would not name (openstout_service.py). A Formula column
  // would therefore be empty on every named row, which measured out as 12
  // dashes in 13 rows the first time this shipped.
  return (
    <div className={`batch__name batch__name--${stateClass} batch__name--empty`}>
      <span className="batch__name-text batch__name-text--muted">
        {row.status === 'error' ? (row.error ?? 'Could not read this input') : label}
        {row.formula ? ` · ${row.formula}` : ''}
      </span>
    </div>
  )
}

function RoundTripCell({ row }) {
  if (row.roundtrip_smiles) {
    return (
      <span className={row.roundtrip_match ? 'batch__rt' : 'batch__rt batch__rt--mismatch'}>
        {row.roundtrip_match ? 'match' : 'mismatch'}
      </span>
    )
  }
  if (row.status === 'pin' || row.status === 'fallback') {
    // A verified tier with no round-trip recorded: say so rather than let the
    // rule under the name imply a check that did not happen.
    return <span className="batch__rt batch__rt--unavailable">unavailable</span>
  }
  return <span className="batch__rt batch__rt--none">—</span>
}

function BatchResults({ job, onForget }) {
  const { jobId, ownerToken, moleculeCount } = job

  const [status, setStatus] = useState(null)
  const [rows, setRows] = useState([])
  const [page, setPage] = useState(0)
  const [error, setError] = useState(null)
  const [gone, setGone] = useState(null)
  const [cancelRequested, setCancelRequested] = useState(false)
  const [busy, setBusy] = useState(null)
  const [drawn, setDrawn] = useState({ key: null, svg: null, error: null, loading: false })

  const [now, setNow] = useState(() => Math.floor(Date.now() / 1000))

  // --- status polling -------------------------------------------------
  // A ref, not state: the loop reads it to decide whether to schedule the
  // next tick, and putting it in state would restart the effect on every
  // poll (the exact shape of bug that made the hero flare dispose itself).
  const liveRef = useRef(true)
  const storedExpiryRef = useRef(job.expiresAt ?? null)

  useEffect(() => {
    liveRef.current = true
    let timer = 0

    const tick = async () => {
      if (!liveRef.current) return
      if (document.hidden) {
        // Nothing to show a hidden tab. Come back when it is visible.
        timer = window.setTimeout(tick, POLL_MS)
        return
      }
      try {
        const next = await fetchJobStatus(jobId)
        if (!liveRef.current) return
        setStatus(next)
        // The submission envelope carries no expires_at -- only this response
        // does -- so the remembered entry is completed here. Without this
        // write the stored expiry stays null forever and jobStore's pruning
        // can never fire, which measured out as expiresAt: null in
        // localStorage after a completed job.
        if (Number.isFinite(next.expires_at) && storedExpiryRef.current !== next.expires_at) {
          // Guarded by a ref, not by the prop: the prop does not change when
          // localStorage does, so comparing against it would rewrite the
          // entry on every single poll.
          storedExpiryRef.current = next.expires_at
          rememberJob({ ...job, expiresAt: next.expires_at })
        }
        setNow(Math.floor(Date.now() / 1000))
        setError(null)
        if (isTerminal(next.status)) return
      } catch (err) {
        if (!liveRef.current) return
        if (err instanceof JobGoneError) {
          setGone(err.message)
          forgetJob(jobId)
          return
        }
        // A blip (or a 429) must not kill the poll: keep the last known
        // status on screen, say what happened, and try again.
        setError(err.message)
      }
      timer = window.setTimeout(tick, POLL_MS)
    }

    void tick()
    return () => {
      liveRef.current = false
      window.clearTimeout(timer)
    }
  }, [jobId, job])

  // --- rows -----------------------------------------------------------
  // `retrievable` comes from the RESULTS response, not the status one -- only
  // JobResultsResponse carries it, and it is what pages must be counted
  // against: `total` is what was submitted, `retrievable` is what can
  // actually be read back, and on a failed job the second is short of the
  // first. Until the first page lands, `total` is the best guess available.
  const [retrievable, setRetrievable] = useState(null)
  const finished = status ? isTerminal(status.status) : false
  const countable = retrievable ?? status?.total ?? 0
  const pages = pageCount(countable)
  // Rows are only worth offering when the server says some can be read back.
  // `retrievable` starts null (nothing fetched yet) and a job that closed
  // cleanly reports its real count; a cancelled one reports 0.
  const hasRows = retrievable === null ? false : retrievable > 0

  const loadPage = useCallback(
    async (which) => {
      try {
        const data = await fetchJobResults(jobId, {
          offset: which * PAGE_SIZE,
          limit: PAGE_SIZE,
        })
        setRows(data.rows ?? [])
        if (Number.isFinite(data.retrievable)) setRetrievable(data.retrievable)
        setError(null)
        return data
      } catch (err) {
        if (err instanceof JobGoneError) {
          setGone(err.message)
          forgetJob(jobId)
          return null
        }
        setError(err.message)
        return null
      }
    },
    [jobId]
  )

  // Rows are fetched when the job reaches a terminal state, and when the page
  // changes after that. Not while it runs: partial pages would reshuffle
  // under the reader on every poll.
  useEffect(() => {
    if (!finished || gone) return
    void loadPage(page)
  }, [finished, page, gone, loadPage])

  // ...and retried while the server is still assembling them. A job that has
  // just gone terminal answers `retrievable: 0` for a few seconds before its
  // rows exist, so this waits rather than reporting an empty job. Bounded, so
  // a job that genuinely kept nothing settles into saying so.
  const [settleTries, setSettleTries] = useState(0)
  const settling = finished && !gone && retrievable === 0 && settleTries < SETTLE_TRIES

  useEffect(() => {
    if (!settling) return
    const timer = window.setTimeout(() => {
      setSettleTries((tries) => tries + 1)
      void loadPage(0)
    }, SETTLE_MS)
    return () => window.clearTimeout(timer)
  }, [settling, settleTries, loadPage])

  // --- controls -------------------------------------------------------
  const stop = async () => {
    setBusy('cancel')
    setCancelRequested(true)
    try {
      const next = await cancelJob(jobId, ownerToken)
      setStatus((current) => ({ ...current, ...next }))
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(null)
    }
  }

  const discard = async () => {
    setBusy('delete')
    try {
      await deleteJob(jobId, ownerToken)
      forgetJob(jobId)
      onForget?.(jobId)
    } catch (err) {
      // 409 for a job that is still running is a real answer, and the
      // server's own sentence explains it better than anything here could.
      setError(err.message)
    } finally {
      setBusy(null)
    }
  }

  const draw = async (row) => {
    const key = rowKey(row)
    if (!row.smiles) return
    if (drawn.key === key) {
      setDrawn({ key: null, svg: null, error: null, loading: false })
      return
    }
    setDrawn({ key, svg: null, error: null, loading: true })
    try {
      const data = await depictMolecule(row.smiles)
      setDrawn({ key, svg: data.depiction_svg ?? null, error: data.error ?? null, loading: false })
    } catch (err) {
      setDrawn({ key, svg: null, error: err.message, loading: false })
    }
  }

  if (gone) {
    return (
      <section className="batch" aria-label="Batch job">
        <p className="batch__gone">{gone}</p>
        <button type="button" className="btn" onClick={() => onForget?.(jobId)}>
          Start again
        </button>
      </section>
    )
  }

  const total = status?.total ?? moleculeCount ?? 0
  const percent = progressPercent({ done: status?.done ?? 0, total })
  const expiry = status ? expiryLabel(status.expires_at, now) : null
  const canCancel = Boolean(ownerToken) && status && !finished
  const canDelete = Boolean(ownerToken) && finished

  return (
    <section className="batch" aria-label="Batch job">
      <header className="batch__head">
        <div className="batch__state">
          <span className="batch__state-word">
            {stateLabel(status?.status ?? 'queued', { cancelRequested })}
          </span>
          <span className="batch__counts">
            {status ? `${status.done} of ${total} molecules` : `${total} molecules`}
            {status?.failed ? ` · ${status.failed} failed` : ''}
          </span>
        </div>

        <div className="batch__actions">
          {canCancel && (
            <button type="button" className="btn" onClick={stop} disabled={busy === 'cancel'}>
              {busy === 'cancel' ? 'Stopping…' : 'Stop'}
            </button>
          )}
          {canDelete && (
            <button type="button" className="btn" onClick={discard} disabled={busy === 'delete'}>
              {busy === 'delete' ? 'Deleting…' : 'Delete results'}
            </button>
          )}
          {!ownerToken && finished && (
            <span className="batch__note">
              Opened from a link, so this browser cannot delete it.
            </span>
          )}
        </div>
      </header>

      {/* aria-valuetext, not just the number: "38 percent" alone does not say
          what is happening, and this bar is the only thing on screen for the
          minutes a big job takes. */}
      <div
        className="batch__progress"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
        aria-valuetext={`${percent}% — ${status?.done ?? 0} of ${total} molecules named`}
      >
        <span className="batch__progress-fill" style={{ width: `${percent}%` }} />
      </div>

      {error && (
        <p className="batch__error" role="status">
          {error}
        </p>
      )}

      {/* Rows do not exist the instant a job goes terminal. Measured against
          the running backend, seconds after a cancel: status "cancelled",
          done 100 of 400, /results answering `retrievable: 0, rows: []` and
          results.csv answering 409 -- the row list is assembled slightly
          later, and a minute after that the same job served 125 rows over
          three pages.
          So this state is "not assembled yet", NOT "kept nothing", and the
          difference matters: an earlier version of this panel declared "a
          stopped job keeps no results", which was simply false. It waits and
          retries instead, and only calls a job empty once the retries are
          spent. It also offers no CSV link until there is something to
          download, because that link 409s in this window. */}
      {finished && !hasRows && (
        <p className="batch__outcome">
          {settling ? (
            `Collecting the molecules that finished (${status?.done ?? 0} of ${total})…`
          ) : (
            <>
              {`${status?.status === 'cancelled' || cancelRequested ? 'Stopped' : 'Ended'} after ${status?.done ?? 0} of ${total} molecules. No rows have appeared yet — a job that was stopped mid-chunk finishes what it started first. `}
              <button
                type="button"
                className="batch__retry"
                onClick={() => {
                  setSettleTries(0)
                  void loadPage(0)
                }}
              >
                Check again
              </button>
            </>
          )}
        </p>
      )}

      {finished && hasRows && (
        <div className="batch__downloads">
          <a className="batch__csv" href={jobResultsCsvUrl(jobId)}>
            Download CSV
          </a>
          {/* The one sentence that stops a results link reading as permanent. */}
          {expiry && (
            <span className="batch__expiry">
              {expiry.charAt(0).toUpperCase() + expiry.slice(1)}
            </span>
          )}
        </div>
      )}

      {finished && rows.length > 0 && (
        <>
          <div className="batch__table-wrap">
            <table className="batch__table">
              <caption className="sr-only">
                Batch results, page {page + 1} of {pages}. Every name carries its
                confidence mark.
              </caption>
              <thead>
                <tr>
                  <th scope="col">#</th>
                  <th scope="col">Input</th>
                  <th scope="col">Name</th>
                  <th scope="col">Round-trip</th>
                  <th scope="col">
                    <span className="sr-only">Structure</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => {
                  const key = rowKey(row)
                  const isDrawn = drawn.key === key
                  return (
                    <Fragment key={key}>
                      <tr className="batch__row">
                        <td className="batch__index">{row.index + 1}</td>
                        <td className="batch__input">
                          <code title={row.input}>{row.input_id ?? row.input}</code>
                        </td>
                        <td>
                          <NameCell row={row} />
                        </td>
                        <td>
                          <RoundTripCell row={row} />
                        </td>
                        <td className="batch__draw-cell">
                          {row.smiles && (
                            <button
                              type="button"
                              className="batch__draw"
                              onClick={() => draw(row)}
                              aria-expanded={isDrawn}
                            >
                              {isDrawn ? 'Hide' : 'Draw'}
                            </button>
                          )}
                        </td>
                      </tr>
                      {isDrawn && (
                        <tr className="batch__drawn-row">
                          <td colSpan={5}>
                            {drawn.loading && <span className="batch__note">Drawing…</span>}
                            {drawn.error && <span className="batch__note">{drawn.error}</span>}
                            {drawn.svg && (
                              <img
                                className="batch__drawn"
                                src={drawn.svg}
                                alt={`Structure of ${row.name ?? row.input}`}
                              />
                            )}
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  )
                })}
              </tbody>
            </table>
          </div>

          {pages > 1 && (
            <nav className="batch__pager" aria-label="Results pages">
              <button
                type="button"
                className="btn"
                onClick={() => setPage((p) => clampPage(p - 1, countable))}
                disabled={page === 0}
              >
                Previous
              </button>
              <span className="batch__page-count">
                Page {page + 1} of {pages}
              </span>
              <button
                type="button"
                className="btn"
                onClick={() => setPage((p) => clampPage(p + 1, countable))}
                disabled={page + 1 >= pages}
              >
                Next
              </button>
            </nav>
          )}
        </>
      )}
    </section>
  )
}

export default BatchResults
