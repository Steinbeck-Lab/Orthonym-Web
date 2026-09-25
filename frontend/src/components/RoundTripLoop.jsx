import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from 'react'
import { cancelJob, translateBatch, TranslateJobQueuedError } from '../lib/api'
import useDepiction from '../lib/useDepiction'
import useReducedMotion from '../lib/useReducedMotion'
import { STATE_CLASS, STATE_SHORT, VERIFIED_STATUSES, stateLabelFor } from '../lib/statuses'
import ChemName from './Typeset'
import TierLamp from './TierLamp'
import TierRule from './TierRule'

/**
 * The About page's centrepiece: the round trip, RUN LIVE and drawn as a loop.
 *
 * Four stations sit on one ink line: the structure goes in (1), the engine
 * writes a name by rule (2), OPSIN reads that name back without ever seeing
 * the structure (3), and the verdict lands (4). The line travels only as far
 * as the molecule really got, and the loop CLOSES only when the tier is a
 * verified one AND the read-back matched (row.roundtrip_match) -- the tier
 * alone is not enough, because a verified tier can come back with a read-back
 * that parsed to a different molecule. A closed loop then wears its tier's
 * rule (double for a PIN, dashed for a fallback); a line that stops short
 * wears its own (dotted for a best effort, faint for no name).
 *
 * THE ROTATION IS THE ARGUMENT, and it is curated for honesty rather than for
 * flattery. Two verified PINs, one fallback, and one outright refusal, each
 * checked against this backend before being listed:
 *
 *   ibuprofen         pin       round-trips clean
 *   caffeine          pin       round-trips clean
 *   morphine          fallback  names it, round-trips, NOT a verified PIN
 *   uranium trioxide  abstain   the engine declines to name it at all
 *
 * It rotates on its own only while it is on screen, not hovered or focused,
 * and not paused -- and a molecule the reader picks stays picked. Only what
 * the reader asked for is announced; the rotation itself is silent.
 *
 * COST DISCIPLINE. Naming is rate-limited per IP (60/min) and every molecule
 * here is fixed, so each is requested at most ONCE per page load: the request
 * is cached per molecule, not per effect, so clicking away mid-request does
 * not throw the answer away. A failure is not cached, so picking the molecule
 * again, or "Try again", retries it.
 */

// `expect` never renders anything -- the real response always wins. It is a
// dev-console tripwire, so an engine change that alters one of these shows up
// instead of silently turning the honest rotation into four happy paths.
const MOLECULES = [
  { key: 'ibuprofen', label: 'Ibuprofen', smiles: 'CC(C)Cc1ccc(cc1)C(C)C(=O)O', expect: 'pin' },
  { key: 'caffeine', label: 'Caffeine', smiles: 'Cn1cnc2c1c(=O)n(C)c(=O)n2C', expect: 'pin' },
  {
    key: 'morphine',
    label: 'Morphine',
    smiles: 'CN1CC[C@]23[C@@H]4[C@H]1Cc1ccc(O)c5c1[C@@]2(CC[C@@H]4O)[C@H](O5)C=C3',
    expect: 'fallback',
  },
  { key: 'uranium-trioxide', label: 'Uranium trioxide', smiles: 'O=[U](=O)=O', expect: 'abstain' },
]

const DWELL_MS = 11000
const DRAW_MS = 2400

// How far round the loop a result gets, as a station index (4 = closed), and
// the sentence the verdict station prints. Read from the whole row, never
// from the tier alone.
function outcome(row) {
  if (!row) return null
  const { status, roundtrip_smiles, roundtrip_match } = row
  if (status === 'error') {
    return { stop: 0, verdict: row.error || 'This structure could not be named.' }
  }
  if (status === 'abstain') {
    return { stop: 1, verdict: 'No name was produced, so there was nothing to read back.' }
  }
  if (!roundtrip_smiles) {
    return { stop: 2, verdict: 'No structure came back from OPSIN, so this name was not checked here.' }
  }
  if (VERIFIED_STATUSES.has(status) && roundtrip_match === true) {
    return {
      stop: 4,
      verdict:
        status === 'pin'
          ? 'OPSIN read the name back to the same molecule.'
          : 'OPSIN read the name back to the same molecule, but its preferred status is not certified.',
    }
  }
  return {
    stop: 3,
    verdict: roundtrip_match
      ? 'OPSIN read the name back to the same molecule. The general engine built it, so it is best effort.'
      : 'OPSIN read the name back to a different molecule.',
  }
}

// What went wrong, in the reader's terms. translateBatch rejects with an
// Error carrying `status` (lib/transport.js httpError), or a TypeError when
// nothing answered at all. A 502 is the proxy saying the backend itself is
// down, so it reads as not answering.
function failureText(error) {
  if (error instanceof TranslateJobQueuedError) {
    return 'The naming service is busy, so this molecule was queued instead of named. Try again shortly.'
  }
  const status = error?.status
  if (status === 429) return 'Too many requests from this address. Wait a minute, then try again.'
  if (status === 503) return 'The naming service is up, but no worker can verify names right now.'
  if (status && status !== 502) return `The naming request failed (HTTP ${status}).`
  return 'The naming service is not answering right now.'
}

// Station centres are MEASURED, not assumed: tile heights change with every
// molecule (a long name wraps, a drawing arrives late), so the loop is
// re-derived from where the four tiles actually sit. Returns the path, where
// each station falls along it (0..1), and its length in px.
function measureLoop(stage, tiles) {
  const s = stage.getBoundingClientRect()
  const c = tiles.map((el) => {
    const r = el.getBoundingClientRect()
    return { x: r.left - s.left + r.width / 2, y: r.top - s.top + r.height / 2 }
  })
  const [a, b, d, e] = c

  // Phone layout: the tiles stack, so the loop becomes a narrow rail down
  // their left edge that turns back up at the bottom.
  if (Math.abs(a.x - b.x) < 8) {
    const right = 27
    const left = 7
    const r = (right - left) / 2
    const run = e.y - a.y
    const total = 2 * run + 2 * Math.PI * r
    return {
      w: s.width,
      h: s.height,
      total,
      path: `M ${right} ${a.y} V ${e.y} A ${r} ${r} 0 0 1 ${left} ${e.y} V ${a.y} A ${r} ${r} 0 0 1 ${right} ${a.y} Z`,
      at: [0, (b.y - a.y) / total, (d.y - a.y) / total, (e.y - a.y) / total],
      nodes: c.map((p) => ({ x: right, y: p.y })),
    }
  }

  const L = a.x
  const R = d.x
  const T = b.y
  const B = e.y
  const r = Math.max(0, Math.min(40, (R - L) / 4, (B - T) / 4))
  const arc = (Math.PI * r) / 2
  const up = a.y - (T + r)
  const across = R - L - 2 * r
  const down = B - T - 2 * r
  const back = B - r - a.y
  const total = up + arc + across + arc + down + arc + across + arc + back
  return {
    w: s.width,
    h: s.height,
    total,
    path:
      `M ${L} ${a.y} V ${T + r} A ${r} ${r} 0 0 1 ${L + r} ${T} H ${R - r} ` +
      `A ${r} ${r} 0 0 1 ${R} ${T + r} V ${B - r} A ${r} ${r} 0 0 1 ${R - r} ${B} ` +
      `H ${L + r} A ${r} ${r} 0 0 1 ${L} ${B - r} Z`,
    at: [
      0,
      (up + arc + (b.x - L - r)) / total,
      (up + arc + across + arc + (d.y - T - r)) / total,
      (up + arc + across + arc + down + arc + (R - r - e.x)) / total,
    ],
    nodes: [
      { x: L, y: a.y },
      { x: b.x, y: T },
      { x: R, y: d.y },
      { x: e.x, y: B },
    ],
  }
}

const targetFor = (geo, stop) => (stop === null || !geo ? 0 : stop >= 4 ? 1 : geo.at[stop])

function crossed(geo, p) {
  const at = geo?.at || [0, 1, 1, 1]
  let n = 1
  for (let i = 1; i < 4; i += 1) if (p >= at[i] - 0.001) n = i + 1
  return n
}

const ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2)

export default function RoundTripLoop() {
  const [index, setIndex] = useState(0)
  const [results, setResults] = useState({}) // molecule key -> { row } | { error }
  const [run, setRun] = useState(0) // bumps on every retry, so the draw restarts
  const [playing, setPlaying] = useState(true)
  const [hovered, setHovered] = useState(false)
  const [visible, setVisible] = useState(true)
  const [announce, setAnnounce] = useState(false)
  const [geo, setGeo] = useState(null)
  const [reached, setReached] = useState(1)
  // Which run finished drawing. `settled` is derived from it, so a finished
  // draw never carries over into the next molecule's first render.
  const [settledFor, setSettledFor] = useState(null)
  const inflight = useRef(new Map())
  const depictions = useRef(new Map())
  const stageRef = useRef(null)
  const tileRefs = useRef([])
  const lineRef = useRef(null)
  const dotRef = useRef(null)
  const geoRef = useRef(null)
  const maskId = useId()
  const reduced = useReducedMotion()

  const molecule = MOLECULES[index]

  const load = useCallback((m) => {
    if (inflight.current.has(m.key)) return
    const request = translateBatch([m.smiles])
      .then((rows) => {
        const row = rows?.[0]
        if (!row) throw new Error('empty response')
        if (import.meta.env?.DEV && row.status !== m.expect) {
          console.warn(
            `[RoundTripLoop] ${m.key} returned "${row.status}", the rotation expects "${m.expect}". Re-check the curated set.`
          )
        }
        setResults((all) => ({ ...all, [m.key]: { row } }))
      })
      .catch((error) => {
        inflight.current.delete(m.key)
        // A queued job would otherwise run on unwatched; its owner token is
        // only ever issued here, so cancel it now.
        if (error instanceof TranslateJobQueuedError && error.ownerToken) {
          cancelJob(error.jobId, error.ownerToken).catch(() => {})
        }
        setResults((all) => ({ ...all, [m.key]: { error } }))
      })
    inflight.current.set(m.key, request)
  }, [])

  useEffect(() => {
    load(molecule)
  }, [molecule, load])

  const entry = results[molecule.key]
  const row = entry?.row || null
  const phase = row ? 'ready' : entry?.error ? 'failed' : 'loading'
  const result = outcome(row)
  const stop = result ? result.stop : null
  const status = row?.status || null
  const tier = status ? STATE_CLASS[status] || status : null
  const runKey = `${index}:${run}`
  const settled = settledFor === runKey
  const retrying = Boolean(entry?.retrying)

  // Rotation: on screen, not hovered or focused, not paused, and never while
  // a molecule is still being drawn.
  const rotating = playing && !hovered && visible && !reduced
  useEffect(() => {
    if (!rotating || !((phase === 'ready' && settled) || (phase === 'failed' && !retrying))) {
      return undefined
    }
    const timer = window.setTimeout(() => {
      setAnnounce(false)
      setIndex((i) => (i + 1) % MOLECULES.length)
    }, DWELL_MS)
    return () => window.clearTimeout(timer)
  }, [rotating, phase, settled, retrying, index])

  useEffect(() => {
    const stage = stageRef.current
    if (!stage || typeof IntersectionObserver === 'undefined') return undefined
    const io = new IntersectionObserver(([e]) => setVisible(e.isIntersecting), { threshold: 0.2 })
    io.observe(stage)
    return () => io.disconnect()
  }, [])

  // Retrying keeps the failure on screen (and the focused button mounted)
  // until the new answer lands.
  const retry = useCallback(() => {
    setResults((all) => ({ ...all, [molecule.key]: { ...all[molecule.key], retrying: true } }))
    setAnnounce(true)
    setRun((n) => n + 1)
    load(molecule)
  }, [molecule, load])

  const pick = useCallback(
    (next) => {
      setPlaying(false) // a molecule the reader chose stays chosen
      setAnnounce(true)
      if (next === index && results[molecule.key]?.error) retry()
      else setIndex(next)
    },
    [index, molecule, results, retry]
  )

  // Drawings, cached per SMILES. Station 1 falls back to drawing the input
  // itself when the naming result carries no picture (a cached refusal).
  const inputSmiles = row && !row.depiction_svg ? molecule.smiles : null
  const rtSmiles = row?.roundtrip_smiles || null
  const cachedIn = inputSmiles ? depictions.current.get(inputSmiles) || null : null
  const cachedRt = rtSmiles ? depictions.current.get(rtSmiles) || null : null
  const fetchedIn = useDepiction(cachedIn ? null : inputSmiles)
  const fetchedRt = useDepiction(cachedRt ? null : rtSmiles)
  const inputSvg = row?.depiction_svg || cachedIn || fetchedIn.svg
  const reparsedSvg = cachedRt || fetchedRt.svg

  useEffect(() => {
    if (inputSmiles && fetchedIn.svg) depictions.current.set(inputSmiles, fetchedIn.svg)
  }, [inputSmiles, fetchedIn.svg])
  useEffect(() => {
    if (rtSmiles && fetchedRt.svg) depictions.current.set(rtSmiles, fetchedRt.svg)
  }, [rtSmiles, fetchedRt.svg])

  // Re-measure whenever the stage or any tile changes size.
  useLayoutEffect(() => {
    const stage = stageRef.current
    if (!stage) return undefined
    const update = () => {
      const tiles = tileRefs.current
      if (tiles.length !== 4 || tiles.some((t) => !t)) return
      const next = measureLoop(stage, tiles)
      geoRef.current = next
      setGeo(next)
    }
    update()
    const ro = new ResizeObserver(update)
    ro.observe(stage)
    tileRefs.current.forEach((t) => t && ro.observe(t))
    return () => ro.disconnect()
  }, [])

  const hasGeo = Boolean(geo)

  // THE ONE AUTHORED MOMENT: the line travels as far as the molecule got.
  // Driven imperatively (a DOM write per frame, a React render only when a
  // station is crossed). The target is re-read from the live geometry every
  // frame, so a re-measure mid-draw (a drawing arriving late) cannot strand
  // the line at a stale fraction.
  useEffect(() => {
    const line = lineRef.current
    const dot = dotRef.current
    setReached(1)
    if (!line || !dot) return undefined
    const paint = (p) => {
      line.style.strokeDashoffset = String(1 - p)
      dot.style.offsetDistance = `${p * 100}%`
    }
    paint(0)
    if (stop === null || !hasGeo) return undefined

    if (reduced || stop === 0) {
      const target = targetFor(geoRef.current, stop)
      paint(target)
      setReached(crossed(geoRef.current, target))
      setSettledFor(runKey)
      return undefined
    }

    let raf = 0
    let last = 1
    const start = performance.now()
    const duration = Math.max(700, DRAW_MS * targetFor(geoRef.current, stop))
    const frame = (now) => {
      const t = Math.min(1, (now - start) / duration)
      const p = ease(t) * targetFor(geoRef.current, stop)
      paint(p)
      const n = crossed(geoRef.current, p)
      if (n !== last) {
        last = n
        setReached(n)
      }
      if (t < 1) raf = requestAnimationFrame(frame)
      else setSettledFor(runKey)
    }
    raf = requestAnimationFrame(frame)
    return () => cancelAnimationFrame(raf)
  }, [stop, hasGeo, reduced, runKey])

  // After the draw, a re-measure (resize, rotation, a font swap, crossing the
  // phone breakpoint) repaints the line straight to its new stop.
  useEffect(() => {
    if (!settled || !geo || !lineRef.current || !dotRef.current) return
    const target = targetFor(geo, stop)
    lineRef.current.style.strokeDashoffset = String(1 - target)
    dotRef.current.style.offsetDistance = `${target * 100}%`
    setReached(crossed(geo, target))
  }, [geo, settled, stop])

  const named = Boolean(row?.name)
  const closed = settled && stop === 4
  const stopped = settled && stop !== null && stop < 4
  const lit = (i) => phase === 'ready' && (i === 0 || i < reached)

  // The stopped line keeps its reach but takes its tier's form: drawn once
  // more, patterned, through a mask cut to the same length.
  const stoppedTarget = stopped && geo ? targetFor(geo, stop) : 0
  const showStoppedForm = stopped && stoppedTarget > 0

  const closedPattern =
    closed && geo && tier === 'fallback'
      ? { strokeDasharray: `${7 / geo.total} ${5 / geo.total}`, strokeDashoffset: 0 }
      : undefined

  const uraniumRow = results['uranium-trioxide']?.row
  const refusalHolds = !uraniumRow || uraniumRow.status === 'abstain'

  let summary = ''
  if (announce && phase === 'ready' && result) {
    summary = named
      ? `${molecule.label}: named ${row.name}. ${result.verdict} ${stateLabelFor(row) || STATE_SHORT[status] || ''}.`
      : `${molecule.label}: ${result.verdict}`
  } else if (announce && phase === 'failed' && !retrying) {
    summary = `${molecule.label}: ${failureText(entry.error)}`
  }

  const stations = [
    <li
      key="in"
      ref={(el) => (tileRefs.current[0] = el)}
      className={`station station--in${lit(0) ? ' is-lit' : ''}`}
    >
      <h3 className="station__title">
        <span className="station__n" aria-hidden="true">1</span>
        <span className="sr-only">Step 1: </span>
        Structure in
      </h3>
      <div className="station__plate">
        {inputSvg ? (
          <img src={inputSvg} alt={`The structure given to the engine: ${molecule.label}`} />
        ) : (
          <span className="station__plate-empty">{molecule.label}</span>
        )}
      </div>
      <code className="station__smiles" title={molecule.smiles}>
        {molecule.smiles}
      </code>
    </li>,
    <li
      key="name"
      ref={(el) => (tileRefs.current[1] = el)}
      className={`station station--name${lit(1) ? ' is-lit' : ''}`}
    >
      <h3 className="station__title">
        <span className="station__n" aria-hidden="true">2</span>
        <span className="sr-only">Step 2: </span>
        Named by rule
      </h3>
      {phase === 'loading' ? (
        <span className="station__waiting" aria-hidden="true">
          <span />
          <span />
          <span />
        </span>
      ) : named ? (
        <div className="station__name-block">
          <p className={`station__name${row.name.length > 40 ? ' station__name--long' : ''}`}>
            <ChemName name={row.name} />
          </p>
          {settled && <TierRule status={status} className="station__rule" />}
        </div>
      ) : phase === 'ready' ? (
        <p className="station__declined">
          {status === 'error' ? 'The structure could not be named.' : 'The engine declined to name this one.'}
        </p>
      ) : (
        <p className="station__declined">Not run.</p>
      )}
      <p className="station__note">Fixed naming rules. No model, no training data.</p>
    </li>,
    <li
      key="back"
      ref={(el) => (tileRefs.current[2] = el)}
      className={`station station--back${lit(2) ? ' is-lit' : ''}`}
    >
      <h3 className="station__title">
        <span className="station__n" aria-hidden="true">3</span>
        <span className="sr-only">Step 3: </span>
        Read back by OPSIN
      </h3>
      <div className="station__plate">
        {named && reparsedSvg ? (
          <img src={reparsedSvg} alt="The structure OPSIN read back from the name" />
        ) : (
          <span className="station__plate-empty">
            {phase === 'ready' && !named ? 'Nothing to read back' : ''}
          </span>
        )}
      </div>
      <code className="station__smiles" title={rtSmiles || ''}>
        {named ? rtSmiles || 'No structure came back from OPSIN.' : '—'}
      </code>
    </li>,
    <li
      key="verdict"
      ref={(el) => (tileRefs.current[3] = el)}
      className={`station station--verdict${lit(3) ? ' is-lit' : ''}`}
    >
      <h3 className="station__title">
        <span className="station__n" aria-hidden="true">4</span>
        <span className="sr-only">Step 4: </span>
        Verdict
      </h3>
      {settled && result ? (
        <>
          <p className="station__tier">
            <TierLamp status={status} />
            <span>{stateLabelFor(row) || STATE_SHORT[status]}</span>
          </p>
          <p className="station__verdict">{result.verdict}</p>
        </>
      ) : (
        <p className="station__verdict station__verdict--waiting">
          {phase === 'failed' ? 'No verdict.' : 'Waiting for the name.'}
        </p>
      )}
    </li>,
  ]

  return (
    <div
      className="loop"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onFocus={() => setHovered(true)}
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget)) setHovered(false)
      }}
    >
      <h2 className="sr-only">The round trip, live</h2>
      <p className="sr-only" aria-live="polite">
        {summary}
      </p>

      <div className="loop__stage" ref={stageRef}>
        {geo && (
          <svg
            className={`loop__track${closed ? ` loop__track--closed loop__track--${tier}` : ''}${
              showStoppedForm ? ` loop__track--stopped loop__track--${tier}` : ''
            }`}
            width={geo.w}
            height={geo.h}
            viewBox={`0 0 ${geo.w} ${geo.h}`}
            aria-hidden="true"
          >
            <path className="loop__route" d={geo.path} />
            <path
              ref={lineRef}
              className="loop__line"
              d={geo.path}
              pathLength="1"
              style={closedPattern}
            />
            {closed && tier === 'pin' && <path className="loop__line-inner" d={geo.path} />}
            {showStoppedForm && (
              <>
                <mask id={maskId} maskUnits="userSpaceOnUse" x="0" y="0" width={geo.w} height={geo.h}>
                  <path
                    d={geo.path}
                    fill="none"
                    stroke="#fff"
                    strokeWidth="12"
                    pathLength="1"
                    strokeDasharray={`${stoppedTarget} 1`}
                  />
                </mask>
                <path className="loop__line-stopped" d={geo.path} mask={`url(#${maskId})`} />
              </>
            )}
            {geo.nodes.map((n, i) => (
              <circle
                key={i}
                className={`loop__node${lit(i) ? ' is-lit' : ''}`}
                cx={n.x}
                cy={n.y}
                r="5"
              />
            ))}
          </svg>
        )}
        <span
          ref={dotRef}
          className={`loop__dot${stopped ? ' loop__dot--stopped' : ''}${closed ? ' loop__dot--home' : ''}`}
          style={geo ? { offsetPath: `path('${geo.path}')` } : { visibility: 'hidden' }}
          aria-hidden="true"
        />

        {/* The hub comes first in the DOM, so a screen reader meets the
            control before the output it drives, as a phone shows it. */}
        <div className="loop__hub">
          <p className="loop__hub-label" id="loop-picker-label">
            Run it on
          </p>
          <div className="loop__picker" role="group" aria-labelledby="loop-picker-label">
            {MOLECULES.map((m, i) => (
              <button
                key={m.key}
                type="button"
                className={i === index ? 'loop__pick loop__pick--on' : 'loop__pick'}
                aria-current={i === index ? 'true' : undefined}
                onClick={() => pick(i)}
              >
                {m.label}
              </button>
            ))}
          </div>
          {phase === 'failed' ? (
            <div className="loop__failed">
              <p className="loop__offline">{failureText(entry.error)}</p>
              <button type="button" className="btn btn--sm" onClick={retry} disabled={retrying}>
                {retrying ? 'Trying again…' : 'Try again'}
              </button>
            </div>
          ) : (
            refusalHolds && <p className="loop__hub-note">One of these it refuses to name.</p>
          )}
          {!reduced && (
            <button
              type="button"
              className="loop__play"
              onClick={() => setPlaying((p) => !p)}
            >
              {playing ? 'Pause the rotation' : 'Resume the rotation'}
            </button>
          )}
        </div>

        <ol className="loop__stations" role="list">
          {stations}
        </ol>
      </div>
    </div>
  )
}
