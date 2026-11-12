import { useCallback, useEffect, useRef, useState } from 'react'
import {
  JobGoneError,
  RateLimitedError,
  cancelJob,
  deleteJob,
  depictMolecule,
  fetchJobResults,
  fetchJobStatus,
  jobResultsCsvUrl,
  jobResultsSdfUrl,
} from '../lib/api'
import {
  PAGE_SIZE,
  clampPage,
  expiryLabel,
  isTerminal,
  latestOnly,
  pageCount,
  progressPercent,
  stateLabel,
} from '../lib/batchJob'
import { outcomeMessage, tierTally } from '../lib/batchTally'
import { limitReasonFor } from '../lib/limitReasons'
import { strippedNote } from '../lib/strippedNote'
import { forgetJob, rememberJob } from '../lib/jobStore'
import { STATE_CLASS, STATE_SHORT, VERIFIED_STATUSES, stateLabelFor } from '../lib/statuses'
import CopyButton from './CopyButton'
import EngineStamp from './EngineStamp'
import Icon from './Icon'
import ReportLink from './ReportLink'
import TierLamp from './TierLamp'
import ChemName, { ChemFormula } from './Typeset'

// One submitted batch: its progress while it runs, then its rows.
//
// Three shapes of honesty are load-bearing here, not decoration:
//
//   1. EVERY row carries its confidence mark. PRODUCT.md principle 3 -- the
//      tier must be visible wherever a name appears, never a footnote -- so
//      each name gets the same rule grammar the result tiles use (double =
//      verified PIN, dashed = verified fallback, dotted = best
//      effort, faint = honest abstain, struck = error). A table is the one
//      place it would be tempting to reduce that to a word in a column.
//   2. The results link is NEVER presented as permanent. The backend keeps a
//      job for 24 hours and then deletes it; `expires_at` is shown in plain
//      words next to the download (design spec section 14, risk 2).
//   3. Every row on the page is drawn (owner instruction 2026-11-12). Batch
//      rows deliberately carry no depiction_svg -- an SVG per row would put
//      tens of megabytes in Redis for a 5,000-row job -- so each is fetched
//      from /api/depict, DRAW_CONCURRENCY at a time. A drawing and a
//      drawing the server refused for good (an unreadable SMILES, over the
//      atom cap) are cached; a failure that may pass (network, 429, 5xx) is
//      not, and offers Retry. A page is up to 50 requests against a budget
//      the small profile sets to 300 a minute: flipping 6+ new pages a minute
//      can hit it, and the first 429 then stops the page's queue.
//
// Polling: every 1.5s while the job is live, which is 40 requests a minute
// against a poll budget of 300 -- and it STOPS on a terminal status. It also
// stops when the tab is hidden, because a backgrounded tab polling a queue is
// pure waste.
const POLL_MS = 1500

// Four, not six: leaves the browser's other connections to this host for the
// results fetch, the downloads and Stop.
const DRAW_CONCURRENCY = 4
// Drawings (and permanent refusals) kept for pages revisited: ten pages'
// worth, least recently used out first, so memory stays bounded on a
// 10,000-row job. /api/depict is also browser-cached for a day; this Map is
// what spares the request altogether.
const DRAW_CACHE_MAX = 500
// How long Retry waits after a 429 that names no Retry-After.
const DRAW_PAUSE_S = 10

function cacheGet(cache, smiles) {
  const hit = cache.get(smiles)
  // Re-inserted on a hit: a Map iterates in insertion order, so the first
  // key is then the least recently USED, not the oldest written.
  if (hit) {
    cache.delete(smiles)
    cache.set(smiles, hit)
  }
  return hit
}

function cachePut(cache, smiles, drawing) {
  cache.delete(smiles)
  cache.set(smiles, drawing)
  if (cache.size > DRAW_CACHE_MAX) cache.delete(cache.keys().next().value)
}

/** The few visible words for a failure that asking again may fix, or null
 *  when it will not: any other 4xx gets the same answer every time. */
function transientReason(err) {
  if (err instanceof RateLimitedError) return 'rate limited'
  if (!Number.isFinite(err?.status)) return 'network error'
  if (err.status >= 500) return 'server error'
  return null
}

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

// The sortable columns, and the direction each one STARTS in.
//
// A first click should give the reader the order they meant, not an arbitrary
// ascending pass they then have to reverse. So the ladder starts strongest
// first, the round-trip starts with the confirmed rows, and the name starts
// A-Z -- and `index` is here because a reader who has sorted needs a way back
// to the order they submitted.
//
// `sr` is what a screen-reader user hears on the button, since the visible
// header is a two-word abbreviation of a longer idea ("Round-trip" for "did
// OPSIN read this name back and get your structure").
const SORT_COLUMNS = [
  { key: 'index', label: 'Input order', sr: 'input order', first: 'asc', asc: 'first to last', desc: 'last to first' },
  { key: 'name', label: 'Name', sr: 'name', first: 'asc', asc: 'A to Z', desc: 'Z to A' },
  { key: 'tier', label: 'Confidence', sr: 'confidence tier', first: 'asc', asc: 'strongest first', desc: 'weakest first' },
  { key: 'roundtrip', label: 'Round-trip', sr: 'round-trip result', first: 'asc', asc: 'confirmed first', desc: 'confirmed last' },
]

/** The sort controls, as a group ABOVE the table rather than clickable
 * column headings.
 *
 * The obvious build is a sortable `th` per column, and it is wrong here for
 * one reason: confidence has no column. It is the rule under the name, and
 * CLAUDE.md's product rule is that a tier is "never reduced to a word in a
 * column" -- so adding a Confidence column to hang a sort off is the one
 * thing this table may not do, and a `th` with no matching `td` is not a
 * table. Sorting by tier is also the sort the reader most wants, since it is
 * what brings every abstain onto one screen, so dropping it was not an
 * option either.
 *
 * One group of four buttons keeps all four sorts in the same idiom, leaves
 * the table structure untouched, and reads as what it is: a control, not a
 * column. The active button carries aria-pressed; its name is the column
 * alone, because a name that stated the direction went stale on reversing.
 * The direction is in the table's caption.
 */
function SortBar({ sort, order, onSort }) {
  return (
    <div className="batch__sortbar" role="group" aria-label="Sort results">
      <span className="batch__sortbar-label" aria-hidden="true">
        Sort
      </span>
      {SORT_COLUMNS.map((column) => {
        const active = sort === column.key
        return (
          <button
            key={column.key}
            type="button"
            className={`batch__sort${active ? ' batch__sort--active' : ''}`}
            aria-pressed={active}
            onClick={() => onSort(column)}
            aria-label={`Sort by ${column.sr}`}
          >
            <span>{column.label}</span>
            {active && (
              <span
                className={`batch__sort-mark${order === 'desc' ? ' batch__sort-mark--desc' : ''}`}
                aria-hidden="true"
              >
                <Icon name="sort" size={12} />
              </span>
            )}
          </button>
        )
      })}
    </div>
  )
}

function StrippedNote({ row }) {
  const note = strippedNote(row)
  return note ? <span className="limit-reason">{note}</span> : null
}

// A name-check row: the name the visitor gave and the verdict on structure,
// in plain words. No tier colour: the verdict is not a confidence tier.
// OPSIN's warnings ride along, because a warned reading (an ambiguous
// locant) can turn a fair name into "Different structure".
function CheckCell({ row }) {
  if (!row.claimed_name) return <span className="batch__note">—</span>
  return (
    <>
      <ChemName name={row.claimed_name} />
      <span className="batch__verdict">
        {row.verdict_text ?? 'Not checked'}
      </span>
      {row.opsin_warnings && (
        <span className="limit-reason">OPSIN warned: {row.opsin_warnings}</span>
      )}
    </>
  )
}

/** The confidence mark, in the same grammar the tiles use. */
function NameCell({ row }) {
  const stateClass = STATE_CLASS[row.status] ?? 'error'
  const label = stateLabelFor(row)
  const reason = limitReasonFor(row)
  if (row.name) {
    return (
      <>
        <div className={`batch__name batch__name--${stateClass}`}>
          {/* No `fresh`: fifty lamps breathing at once is a light show, not
              a signal. */}
          <TierLamp row={row} />
          <span className="batch__name-text">
            <ChemName name={row.name} />
          </span>
          {/* `row.name`, the data object -- NEVER the typeset DOM above it.
              Typeset renders `0^4,9` as a superscript, and copying what the
              reader SEES would put a name on the clipboard that no parser can
              read back. Every copy path in this app reads the string. */}
          <CopyButton text={row.name} label={`Copy name for row ${row.index + 1}`} />
        </div>
        {/* The label in plain text under the rule, on every named row. With
            only the rule and a hover tooltip, a demoted "Name not checked
            here" row (OPSIN verify off) looked exactly like an engine
            best-effort name: the same dots, nothing to read. */}
        {label && <span className="batch__state-label">{label}</span>}
      </>
    )
  }
  // No name: the abstain and error states still need their own mark, or a
  // reader cannot tell "the engine refused" from "the input could not be named".
  //
  // The formula rides along HERE rather than in a column of its own, because
  // the engine only ever fills it for an abstain -- it is the consolation for
  // a molecule it would not name (orthonym_service.py). A Formula column
  // would therefore be empty on every named row, which measured out as 12
  // dashes in 13 rows the first time this shipped.
  return (
    <div className={`batch__name batch__name--${stateClass}`}>
      <TierLamp row={row} />
      <span className="batch__name-text batch__name-text--muted">
        {row.status === 'error' ? (row.error ?? 'This input could not be named') : label}
        {row.formula ? (
          <>
            {' · '}
            <ChemFormula formula={row.formula} />
          </>
        ) : null}
        {reason && <span className="limit-reason">{reason}</span>}
      </span>
    </div>
  )
}

/** The outcome, counted by tier.
 *
 * The panel used to report `done of total` and `N failed`, and `failed` only
 * ever counts a row the engine could not produce. A molecule it honestly
 * DECLINED is an abstain -- a successful row with no name -- so a run that
 * abstained on a third of its input reported "0 failed" and read as a clean
 * sweep. Those numbers reached the CSV and nothing else.
 *
 * So: the whole ladder, in the ladder's order, each count wearing the same
 * rule its rows wear. Two rules hold it honest --
 *
 *   1. `named` and `not named` are separate figures and the per-tier list
 *      sits right under them, because "the engine declined" and "the input
 *      could not be named" must not merge into one number (PRODUCT.md: a
 *      best-effort name must never be conflated with a verified one, and an
 *      abstain is the engine working correctly, not a fault).
 *   2. While the job runs these counts are PARTIAL, so the heading says "so
 *      far" and counts against what has been counted -- never against the
 *      job's declared total, which would report work-in-progress as a
 *      shortfall.
 */
function BatchTally({ counts, finished, filter = [], onToggle = null, onClear, tallyRef }) {
  const rows = tierTally(counts)
  if (rows.length === 0) return null
  return (
    <div className="batch__tally" ref={tallyRef}>
      {/* The reading in words, so nobody has to add the chips up. It states
          only what the tier counts support -- see outcomeMessage on why it
          makes no round-trip claim. Not a live region: it changes on every
          poll while the job runs; the panel's own status line announces the
          state changes instead. */}
      <p className="batch__tally-say">
        {outcomeMessage(counts, { finished })}
      </p>
      <ul className="batch__tally-list">
        {rows.map((row) => (
          <li
            key={row.status}
            className={`batch__tally-item batch__tally-item--${row.className}`}
          >
            {/* A toggle once the rows can be read back: it filters the table
                to this tier. Before that the counts are partial and there is
                no table to filter, so they stay plain text. */}
            {onToggle ? (
              <button
                type="button"
                className="batch__tally-toggle"
                aria-pressed={filter.includes(row.status)}
                onClick={() => onToggle(row.status)}
              >
                <TallyCount row={row} />
              </button>
            ) : (
              <TallyCount row={row} />
            )}
          </li>
        ))}
        {filter.length > 0 && (
          <li>
            <button type="button" className="batch__tally-clear" onClick={onClear}>
              Show all
            </button>
          </li>
        )}
      </ul>
    </div>
  )
}

function TallyCount({ row }) {
  return (
    <>
      <span className="batch__tally-count">{row.count}</span>
      <span className="batch__tally-label">{row.label}</span>
    </>
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
  if (VERIFIED_STATUSES.has(row.status)) {
    // A verified tier with no round-trip recorded: say so rather than let the
    // rule under the name imply a check that did not happen. The tier list
    // comes from statuses.js, whose own header warns that two copies of
    // "which tiers claim a round-trip" is how a tier ends up displayed as
    // more confident than it is -- Tile.jsx asks the same question the same
    // way.
    return <span className="batch__rt batch__rt--unavailable">unavailable</span>
  }
  return <span className="batch__rt batch__rt--none">—</span>
}

// `persist` false keeps the job out of jobStore, which is Home's list to
// restore on load: a name-check job (/check) must not reappear on Home.
// `onFinished(jobId)` runs once the job is over (terminal or gone), so the
// page can tell a finished panel, which a new inline result may replace, from
// a running one, which it must not.
function BatchResults({ job, onForget, onFinished, persist = true }) {
  const { jobId, ownerToken, moleculeCount } = job
  // A ref, so a new callback each render does not restart the poll below.
  const onFinishedRef = useRef(onFinished)
  onFinishedRef.current = onFinished

  const [status, setStatus] = useState(null)
  const isCheck = status?.kind === 'check'
  const [rows, setRows] = useState([])
  const [page, setPage] = useState(0)
  const [error, setError] = useState(null)
  const [gone, setGone] = useState(null)
  const [cancelRequested, setCancelRequested] = useState(false)
  const [busy, setBusy] = useState(null)
  // This page's SMILES -> { svg } | { error } (permanent, the server's
  // reason) | { error, reason, retry: true } (may pass if asked again).
  // drawCache holds the first two across pages; drawQueue is the page's
  // queue, which Retry adds to.
  const [drawings, setDrawings] = useState({})
  const drawCache = useRef(new Map())
  const drawQueue = useRef(null)
  // After a 429, Retry waits this long (epoch ms); 0 when not paused.
  const [drawPausedUntil, setDrawPausedUntil] = useState(0)
  // The sort is SERVER-SIDE: it orders the whole job, then the server slices
  // the page. Sorting the 50 rows already in `rows` would only reorder the
  // page on screen, which is not what "sort through the pages" means.
  const [sort, setSort] = useState('index')
  const [order, setOrder] = useState('asc')

  const [now, setNow] = useState(() => Math.floor(Date.now() / 1000))

  // --- status polling -------------------------------------------------
  // A ref, not state: the loop reads it to decide whether to schedule the
  // next tick, and putting it in state would restart the effect on every
  // poll (the exact shape of bug that made the hero flare dispose itself).
  const liveRef = useRef(true)
  const storedExpiryRef = useRef(job.expiresAt ?? null)
  // Stop unmounts when the job goes terminal. If it had focus then, focus
  // goes to the state line rather than falling to <body>.
  const stopRef = useRef(null)
  const stateRef = useRef(null)
  const refocusState = useRef(false)
  const noteStopFocus = () => {
    if (stopRef.current && document.activeElement === stopRef.current) refocusState.current = true
  }

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
        if (isTerminal(next.status)) noteStopFocus()
        setStatus(next)
        setNow(Math.floor(Date.now() / 1000))
        setError(null)
        if (isTerminal(next.status)) {
          // Finished, failed or stopped: the job will never need stopping
          // again, so the one reason to keep its token in localStorage is
          // spent. Forgetting it here is what makes a reload CLEAR the page.
          // Kept, a finished batch came back on every load and survived a
          // hard reload -- which cannot clear localStorage -- so the panel
          // could not be dismissed at all. This session keeps its own copy
          // in React state, so Delete results still works right here.
          forgetJob(jobId)
          onFinishedRef.current?.(jobId)
          return
        }
        // The submission envelope carries no expires_at -- only this response
        // does -- so the remembered entry is completed here. Without this
        // write the stored expiry stays null forever and jobStore's pruning
        // can never fire, which measured out as expiresAt: null in
        // localStorage after a completed job.
        if (persist && Number.isFinite(next.expires_at) && storedExpiryRef.current !== next.expires_at) {
          // Guarded by a ref, not by the prop: the prop does not change when
          // localStorage does, so comparing against it would rewrite the
          // entry on every single poll.
          storedExpiryRef.current = next.expires_at
          // The status goes with it: rememberJob refuses a terminal one, so
          // this cannot resurrect an entry the branch above just forgot.
          rememberJob({ ...job, expiresAt: next.expires_at, status: next.status })
        }
      } catch (err) {
        if (!liveRef.current) return
        if (err instanceof JobGoneError) {
          setGone(err.message)
          forgetJob(jobId)
          onFinishedRef.current?.(jobId)
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
  }, [jobId, job, persist])

  // --- rows -----------------------------------------------------------
  // `retrievable` comes from the RESULTS response, not the status one -- only
  // JobResultsResponse carries it, and it is what pages must be counted
  // against: `total` is what was submitted, `retrievable` is what can
  // actually be read back, and on a failed job the second is short of the
  // first. Until the first page lands, `total` is the best guess available.
  const [retrievable, setRetrievable] = useState(null)
  // The tiers the table is filtered to (empty = every row), and how many rows
  // they hold. Pages count against `matched`, which the server sets equal to
  // `retrievable` when nothing is filtered.
  const [filter, setFilter] = useState([])
  const [matched, setMatched] = useState(null)
  // Quick toggles send overlapping requests; only the newest may fill the table.
  const trackPage = useRef(latestOnly())
  const tallyRef = useRef(null)
  const finished = status ? isTerminal(status.status) : false
  const countable = matched ?? retrievable ?? status?.total ?? 0
  const pages = pageCount(countable)
  // Rows are only worth offering when the server says some can be read back.
  // `retrievable` starts null (nothing fetched yet) and a job that closed
  // cleanly reports its real count; a cancelled one reports 0.
  const hasRows = retrievable === null ? false : retrievable > 0

  const loadPage = useCallback(
    async (which) => {
      try {
        const { stale, value: data } = await trackPage.current(
          fetchJobResults(jobId, {
            offset: which * PAGE_SIZE,
            limit: PAGE_SIZE,
            sort,
            order,
            statuses: filter,
          })
        )
        if (stale) return null
        setRows(data.rows ?? [])
        if (Number.isFinite(data.retrievable)) setRetrievable(data.retrievable)
        if (Number.isFinite(data.matched)) setMatched(data.matched)
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
    [jobId, sort, order, filter]
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

  // Re-sorting takes the reader back to page 1. Staying on page 4 of a new
  // ordering would show them rows 151-200 of a list they have not seen the
  // start of, which reads as the sort having done nothing.
  const applySort = (column) => {
    if (sort === column.key) {
      setOrder((current) => (current === 'asc' ? 'desc' : 'asc'))
    } else {
      setSort(column.key)
      setOrder(column.first)
    }
    setPage(0)
  }

  // A filter change also goes back to page 1: page 4 of the old view may not
  // exist in the new one.
  const toggleTier = (tier) => {
    setFilter((current) =>
      current.includes(tier) ? current.filter((t) => t !== tier) : [...current, tier]
    )
    setPage(0)
  }
  // "Show all" removes itself, so focus moves to the first tier toggle rather
  // than falling back to the page.
  const filterNote = filter.length
    ? `, showing only ${filter.map((s) => STATE_SHORT[s] ?? s).join(' and ')}`
    : ''
  const clearFilter = () => {
    setFilter([])
    setPage(0)
    requestAnimationFrame(() => tallyRef.current?.querySelector('.batch__tally-toggle')?.focus())
  }

  // --- controls -------------------------------------------------------
  const stop = async () => {
    // aria-disabled, not disabled, while stopping: a disabled button drops
    // the keyboard focus it holds, so the guard lives here instead.
    if (busy === 'cancel') return
    setBusy('cancel')
    setCancelRequested(true)
    try {
      const next = await cancelJob(jobId, ownerToken)
      if (isTerminal(next?.status)) noteStopFocus()
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

  // Drawn a few at a time, not 50 at once: the browser has ~6 connections
  // per host, and a full page of depictions queued in front of the results
  // fetch, the downloads and Stop. Leaving the page aborts what is left, so a
  // page the reader has gone from stops spending the depict budget.
  //
  // Workers pull from `queue.todo` until it is empty; Retry pushes one SMILES
  // onto the same queue and tops the workers up, so it never re-runs the page
  // effect (which would abort what is in flight and blank every cell).
  const runDrawQueue = useCallback((queue) => {
    const { signal } = queue.controller
    const work = async () => {
      queue.active += 1
      try {
        while (queue.todo.length && !signal.aborted) {
          const smiles = queue.todo.shift()
          let drawing
          try {
            const data = await depictMolecule(smiles, signal)
            if (signal.aborted) return
            // A 2xx with `error` is the server refusing for good (unreadable,
            // over MAX_DEPICT_ATOMS): cached, and no Retry.
            drawing = data.depiction_svg
              ? { svg: data.depiction_svg }
              : { error: data.error ?? 'No drawing returned.' }
            cachePut(drawCache.current, smiles, drawing)
          } catch (err) {
            if (signal.aborted) return
            const reason = transientReason(err)
            if (!reason) {
              drawing = { error: err.message }
              cachePut(drawCache.current, smiles, drawing)
            } else if (err instanceof RateLimitedError) {
              // The budget is spent: asking for the rest now only earns more
              // 429s. Stop the page and mark what is left, retryable.
              const notDrawn = { error: err.message, reason, retry: true }
              const rest = queue.todo.splice(0)
              setDrawPausedUntil(Date.now() + (err.retryAfterSeconds ?? DRAW_PAUSE_S) * 1000)
              setDrawings((all) => {
                const next = { ...all, [smiles]: notDrawn }
                for (const other of rest) next[other] = notDrawn
                return next
              })
              continue
            } else {
              drawing = { error: err.message, reason, retry: true }
            }
          }
          setDrawings((all) => ({ ...all, [smiles]: drawing }))
        }
      } finally {
        queue.active -= 1
      }
    }
    // `work` counts itself and takes its first SMILES synchronously, so this
    // starts no more workers than there are SMILES left.
    while (queue.active < DRAW_CONCURRENCY && queue.todo.length && !signal.aborted) void work()
  }, [])

  useEffect(() => {
    const queue = { controller: new AbortController(), todo: [], active: 0 }
    const ready = {}
    for (const smiles of new Set(rows.map((row) => row.smiles).filter(Boolean))) {
      const hit = cacheGet(drawCache.current, smiles)
      if (hit) ready[smiles] = hit
      else queue.todo.push(smiles)
    }
    setDrawings(ready)
    drawQueue.current = queue
    runDrawQueue(queue)
    return () => queue.controller.abort()
  }, [rows, runDrawQueue])

  // Retry opens again when the 429's wait is over.
  useEffect(() => {
    if (!drawPausedUntil) return undefined
    const timer = window.setTimeout(() => setDrawPausedUntil(0), Math.max(0, drawPausedUntil - Date.now()))
    return () => window.clearTimeout(timer)
  }, [drawPausedUntil])

  const drawPaused = drawPausedUntil > 0
  const retryDrawing = (smiles, cell) => {
    const queue = drawQueue.current
    if (drawPaused || !queue || queue.controller.signal.aborted) return
    // The button is about to become "Drawing…": hold focus on its cell
    // rather than let it fall to <body>.
    cell?.focus()
    setDrawings((all) => {
      const next = { ...all }
      delete next[smiles]
      return next
    })
    if (!queue.todo.includes(smiles)) queue.todo.push(smiles)
    runDrawQueue(queue)
  }

  // Focus Stop held when it unmounted goes to the state line.
  const canCancel = Boolean(ownerToken) && Boolean(status) && !finished
  useEffect(() => {
    if (canCancel || !refocusState.current) return
    refocusState.current = false
    stateRef.current?.focus()
  }, [canCancel])

  if (gone) {
    return (
      <section className="batch" aria-label="Batch job">
        <h2 className="sr-only">Batch job</h2>
        <p className="batch__gone">{gone}</p>
        <button type="button" className="btn" onClick={() => onForget?.(jobId)}>
          <Icon name="refresh" />
          Start again
        </button>
      </section>
    )
  }

  const total = status?.total ?? moleculeCount ?? 0
  const percent = progressPercent({ done: status?.done ?? 0, total })
  const expiry = status ? expiryLabel(status.expires_at, now) : null
  const stateWord = stateLabel(status?.status ?? 'queued', { cancelRequested })
  // What the panel's status line says: the state, and the outcome once the
  // job is over. It changes on a state change only -- the tally under the
  // bar changes on every poll and is not a live region.
  const announcement = !status
    ? ''
    : finished
      ? `${stateWord}. ${outcomeMessage(status.counts, { finished: true })}`
      : stateWord
  // The switches this job was named with, for "Report SMILES on GitHub". One
  // object for the job, not one per row.
  const jobSettings = status && {
    bestEffort: status.best_effort,
    verify: status.verify,
    stripSalts: status.strip_salts,
  }
  const canDelete = Boolean(ownerToken) && finished
  const sortColumn = SORT_COLUMNS.find((c) => c.key === sort)

  return (
    <section className="batch" aria-label="Batch job">
      {/* For jumping to results by heading; the page's own headings skip
          from its h1 to here. */}
      <h2 className="sr-only">Batch job</h2>
      <p className="sr-only" role="status">
        {announcement}
      </p>
      <header className="batch__head">
        <div className="batch__state" ref={stateRef} tabIndex={-1}>
          <span className="batch__state-word">{stateWord}</span>
          <span className="batch__counts">
            {status ? `${status.done} of ${total} molecules` : `${total} molecules`}
            {status?.failed && !tierTally(status?.counts).length
              ? ` · ${status.failed} failed`
              : ''}
          </span>
        </div>

        <div className="batch__actions">
          {canCancel && (
            <button
              type="button"
              className="btn"
              ref={stopRef}
              onClick={stop}
              aria-disabled={busy === 'cancel' || undefined}
            >
              <Icon name="stop" size={13} />
              {busy === 'cancel' ? 'Stopping…' : 'Stop'}
            </button>
          )}
          {canDelete && (
            <button type="button" className="btn" onClick={discard} disabled={busy === 'delete'}>
              <Icon name="trash" size={13} />
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

      <BatchTally
        counts={status?.counts}
        finished={finished}
        filter={filter}
        onToggle={finished && hasRows ? toggleTier : null}
        onClear={clearFilter}
        tallyRef={tallyRef}
      />

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
            {filter.length ? 'Download CSV (all rows)' : 'Download CSV'}
          </a>
          <a className="batch__csv" href={jobResultsSdfUrl(jobId)}>
            {filter.length ? 'Download SDF (all rows)' : 'Download SDF'}
          </a>
          {/* The one sentence that stops a results link reading as permanent. */}
          {expiry && (
            <span className="batch__expiry">
              {expiry.charAt(0).toUpperCase() + expiry.slice(1)}
            </span>
          )}
          <EngineStamp rows={rows} />
        </div>
      )}

      {finished && hasRows && filter.length > 0 && matched === 0 && (
        <p className="batch__outcome">No rows in this job have the selected confidence.</p>
      )}

      {finished && rows.length > 0 && (
        <>
          <SortBar sort={sort} order={order} onSort={applySort} />
          {/* Focusable and named: it scrolls sideways, and a keyboard can only
              scroll what it can reach. */}
          <div className="batch__table-wrap" tabIndex={0} role="region" aria-label="Batch results table">
            <table className="batch__table">
              <caption className="sr-only">
                Batch results, page {page + 1} of {pages}, sorted by {sortColumn?.sr},{' '}
                {sortColumn?.[order]}
                {filterNote}. Every name carries its
                confidence mark.
              </caption>
              <thead>
                <tr>
                  <th scope="col">#</th>
                  <th scope="col">Input</th>
                  <th scope="col">Name</th>
                  {isCheck && <th scope="col">Claimed name</th>}
                  <th scope="col">Round-trip</th>
                  <th scope="col">Structure</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => {
                  const key = rowKey(row)
                  const drawing = row.smiles ? drawings[row.smiles] : null
                  return (
                      <tr key={key} className="batch__row">
                        <td className="batch__index">{row.index + 1}</td>
                        <td className="batch__input">
                          {/* With an ID from the file, the SMILES under it as
                              secondary text: in a title alone, no keyboard or
                              touch reader could reach it. */}
                          <code title={row.input}>{row.input_id ?? row.input}</code>
                          {row.input_id && (
                            <code className="batch__input-smiles">{row.input}</code>
                          )}
                        </td>
                        <td>
                          <NameCell row={row} />
                          <StrippedNote row={row} />
                          {/* In the Name cell, not beside Draw: an unnamed row
                              has no name to squeeze, while a pill in the last
                              column widened it for EVERY row on the page. */}
                          <ReportLink
                            row={row}
                            where="Home (batch)"
                            settings={jobSettings}
                          />
                        </td>
                        {isCheck && (
                          <td>
                            <CheckCell row={row} />
                          </td>
                        )}
                        <td>
                          <RoundTripCell row={row} />
                        </td>
                        {/* tabIndex -1: Retry hands focus to its cell as it
                            turns into "Drawing…". */}
                        <td className="batch__structure" tabIndex={-1}>
                          {row.smiles && !drawing && <span className="batch__note">Drawing…</span>}
                          {/* A failure that may pass: a few words in caption
                              capitals, the server's sentence in a title (the
                              full 429 text wrapped over many lines in this
                              180px cell). */}
                          {drawing?.error && drawing.retry && (
                            <span className="batch__not-drawn">
                              <span className="batch__note" title={drawing.error}>
                                Not drawn — {drawing.reason}
                              </span>
                              <button
                                type="button"
                                className="batch__redraw"
                                onClick={(event) => retryDrawing(row.smiles, event.currentTarget.closest('td'))}
                                aria-disabled={drawPaused || undefined}
                                aria-label={`Retry drawing the structure for row ${row.index + 1}`}
                              >
                                Retry
                              </button>
                            </span>
                          )}
                          {/* A refusal for good: the server's own reason, in
                              sentence case, and no Retry -- it would say the
                              same again. */}
                          {drawing?.error && !drawing.retry && (
                            <span className="batch__draw-reason">{drawing.error}</span>
                          )}
                          {drawing?.svg && (
                            <img
                              className="batch__drawn"
                              src={drawing.svg}
                              alt={`Structure of ${row.name ?? row.input}`}
                            />
                          )}
                        </td>
                      </tr>
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
                aria-disabled={page === 0 || undefined}
              >
                <Icon name="back" size={13} />
                Previous
              </button>
              <span className="batch__page-count">
                Page {page + 1} of {pages}
              </span>
              <button
                type="button"
                className="btn"
                onClick={() => setPage((p) => clampPage(p + 1, countable))}
                aria-disabled={page + 1 >= pages || undefined}
              >
                Next
                <Icon name="forward" size={13} />
              </button>
            </nav>
          )}
        </>
      )}
    </section>
  )
}

export default BatchResults
