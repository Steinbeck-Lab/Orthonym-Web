import { useCallback, useEffect, useRef, useState } from 'react'
import { translateBatch } from '../lib/api'
import useDepiction from '../lib/useDepiction'
import useReducedMotion from '../lib/useReducedMotion'
import { STATE_CLASS, STATE_LABEL } from '../lib/statuses'
import ChemName from './Typeset'

/**
 * The About page's centrepiece: Orthonym's own round-trip check, RUN LIVE.
 *
 * Every other naming tool asserts its accuracy in prose. This one can show it,
 * so the page shows it: a real molecule goes through the real engine on the
 * real backend, OPSIN reads the name back independently, and both structures
 * are drawn side by side for the reader to compare with their own eyes. The
 * three paragraphs this replaced described that sequence; this performs it.
 *
 * THE ROTATION IS THE ARGUMENT, and it is curated for honesty rather than for
 * flattery. Two verified PINs, one fallback, and one outright refusal -- every
 * status was checked against this backend before being listed here, not
 * assumed:
 *
 *   ibuprofen         pin       round-trips clean
 *   caffeine          pin       round-trips clean
 *   morphine          fallback  names it, round-trips, NOT a preferred name
 *   uranium trioxide  abstain   the engine declines to name it at all
 *
 * A proof that only ever shows wins is marketing. The abstain case is the one
 * that makes the other three worth believing, so it is in the rotation at
 * equal weight and gets the same staging, not a footnote.
 *
 * COST DISCIPLINE. Naming is rate-limited per IP (60/min) and every molecule
 * here is fixed, so each is fetched at most ONCE per page load and cached in a
 * ref; rotating back to a molecule already seen costs nothing. Nothing is
 * prefetched -- the first molecule loads on mount, the rest as they are
 * reached, so a reader who never scrolls pays for one call.
 */

// Curated, and every `status` below was verified live against this backend.
// `expect` is not used to RENDER anything -- the real response always wins --
// it is here so a future engine change that alters one of these shows up as a
// mismatch in the dev console rather than silently turning the honest
// rotation into four happy paths.
const MOLECULES = [
  {
    key: 'ibuprofen',
    label: 'Ibuprofen',
    smiles: 'CC(C)Cc1ccc(cc1)C(C)C(=O)O',
    expect: 'pin',
  },
  {
    key: 'caffeine',
    label: 'Caffeine',
    smiles: 'Cn1cnc2c1c(=O)n(C)c(=O)n2C',
    expect: 'pin',
  },
  {
    key: 'morphine',
    label: 'Morphine',
    smiles: 'CN1CC[C@]23[C@@H]4[C@H]1Cc1ccc(O)c5c1[C@@]2(CC[C@@H]4O)[C@H](O5)C=C3',
    expect: 'fallback',
  },
  {
    key: 'uranium-trioxide',
    label: 'Uranium trioxide',
    smiles: 'O=[U](=O)=O',
    expect: 'abstain',
  },
]

const DWELL_MS = 11000

// What the verdict line says, per status. The words are the product's own
// vocabulary (lib/statuses.js owns the tier labels); this only adds the
// one-line reading of what the round trip proved.
const VERDICT = {
  pin: 'OPSIN read the name back to the same molecule.',
  fallback: 'OPSIN read the name back to the same molecule — but this is not a preferred name.',
  best_effort: 'OPSIN could not confirm this name.',
  abstain: 'No name was produced, so there was nothing to read back.',
  error: 'This structure could not be read.',
}

export default function RoundTripProof() {
  const [index, setIndex] = useState(0)
  const [row, setRow] = useState(null)
  const [phase, setPhase] = useState('loading') // loading | ready | failed
  const [paused, setPaused] = useState(false)
  const cache = useRef(new Map())
  // The re-parsed DEPICTION is cached beside the row it belongs to. Without
  // this the naming result was cached and its picture was not, so every lap of
  // a four-slide rotation re-fetched the same four SVGs forever -- against the
  // header's own promise that "rotating back to a molecule already seen costs
  // nothing", and against a per-IP depiction rate limit.
  const depictions = useRef(new Map())
  const reduced = useReducedMotion()

  const molecule = MOLECULES[index]

  // One fetch per molecule per page load; the rotation is fixed, so a second
  // visit to the same slide is free.
  useEffect(() => {
    let cancelled = false
    const cached = cache.current.get(molecule.key)
    if (cached) {
      setRow(cached)
      setPhase('ready')
      return undefined
    }
    setPhase('loading')
    setRow(null)
    translateBatch([molecule.smiles])
      .then((rows) => {
        if (cancelled) return
        const result = rows?.[0]
        if (!result) {
          setPhase('failed')
          return
        }
        if (import.meta.env?.DEV && result.status !== molecule.expect) {
          // Not a crash: the real answer always ships. This is the tripwire
          // that stops the honest rotation drifting into four happy paths.
          console.warn(
            `[RoundTripProof] ${molecule.key} returned "${result.status}", the rotation expects "${molecule.expect}". Re-check the curated set.`
          )
        }
        cache.current.set(molecule.key, result)
        setRow(result)
        setPhase('ready')
      })
      .catch(() => {
        if (!cancelled) setPhase('failed')
      })
    return () => {
      cancelled = true
    }
  }, [molecule])

  // Auto-advance, unless the reader is interacting with it or has asked for
  // less motion. A carousel that moves under a reader mid-sentence is worse
  // than one that does not move at all.
  useEffect(() => {
    if (paused || reduced || phase !== 'ready') return undefined
    const timer = window.setTimeout(
      () => setIndex((i) => (i + 1) % MOLECULES.length),
      DWELL_MS
    )
    return () => window.clearTimeout(timer)
  }, [paused, reduced, phase, index])

  const show = useCallback((next) => {
    setIndex(next)
    setPaused(true)
  }, [])

  // The re-parsed structure is not part of the naming result -- only the
  // INPUT's depiction ships with it -- so it is drawn separately, exactly as
  // a Translate tile does it. Passing null once it is cached is what stops the
  // hook re-fetching: `useDepiction(null)` is a documented no-op.
  const rtSmiles = row?.roundtrip_smiles || null
  const cachedSvg = rtSmiles ? depictions.current.get(rtSmiles) || null : null
  const fetched = useDepiction(cachedSvg ? null : rtSmiles)
  const reparsedSvg = cachedSvg || fetched.svg

  useEffect(() => {
    if (rtSmiles && fetched.svg) depictions.current.set(rtSmiles, fetched.svg)
  }, [rtSmiles, fetched.svg])

  const named = Boolean(row?.name)
  const verdict = row ? VERDICT[row.status] || null : null
  const stateLabel = row ? STATE_LABEL[row.status] : null

  const stageClass = `rtp${reduced ? ' rtp--still' : ''}${phase === 'ready' ? ' rtp--ready' : ''}`

  return (
    <section
      className={stageClass}
      aria-label="A round-trip check, running live"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocusCapture={() => setPaused(true)}
    >
      <header className="rtp__head">
        <h2 className="rtp__title">Watch it check itself</h2>
        <p className="rtp__lede">
          Every name below is produced live by the engine on this server, then read back by
          OPSIN — an independent parser that has never seen the structure. Compare the two
          drawings yourself.
        </p>
      </header>

      {/* The whole sequence is one aria-live region: a screen reader hears the
          finished result once, rather than each of the five stages arriving
          separately as the animation plays them in. */}
      <div className="rtp__stage" aria-live="polite" aria-busy={phase === 'loading'}>
        {phase === 'failed' ? (
          <p className="rtp__offline">
            The naming service is not answering right now, so this demonstration cannot run.
            Everything it would show is described in <a href="#key">the key</a> below.
          </p>
        ) : (
          <ol className="rtp__flow" role="list">
            {/* 1 — what goes in */}
            <li className="rtp__step rtp__step--in">
              <span className="rtp__step-label">You give it a structure</span>
              <code className="rtp__smiles">{molecule.smiles}</code>
            </li>

            {/* 2 — the engine names it, by rule */}
            <li className="rtp__step rtp__step--name">
              <span className="rtp__step-label">
                The engine applies IUPAC rules — no model, no training data
              </span>
              {phase === 'loading' ? (
                <span className="rtp__waiting" aria-hidden="true">
                  <span className="rtp__waiting-dash" />
                  <span className="rtp__waiting-dash" />
                  <span className="rtp__waiting-dash" />
                </span>
              ) : named ? (
                <p className="rtp__name">
                  <ChemName name={row.name} />
                </p>
              ) : (
                <p className="rtp__declined">
                  It declined to name this one.
                  <span className="rtp__declined-note">
                    Refusing is a result, not an error — and on the benchmark it is counted as a
                    failure rather than quietly dropped.
                  </span>
                </p>
              )}
            </li>

            {/* 3 — OPSIN reads it back. Only meaningful when there IS a name. */}
            {named && (
              <li className="rtp__step rtp__step--back">
                <span className="rtp__step-label">OPSIN reads that name back, independently</span>
                {row.roundtrip_smiles ? (
                  <code className="rtp__smiles">{row.roundtrip_smiles}</code>
                ) : (
                  <p className="rtp__declined">OPSIN could not parse the name.</p>
                )}
              </li>
            )}

            {/* 4 — the comparison the reader can make themselves */}
            {named && (
              <li className="rtp__step rtp__step--compare">
                <span className="rtp__step-label">Same molecule?</span>
                <div className="rtp__pair">
                  <figure className="rtp__panel">
                    {row.depiction_svg ? (
                      <img src={row.depiction_svg} alt={`The structure you gave it, ${molecule.label}`} />
                    ) : (
                      <span className="rtp__panel-empty" aria-hidden="true" />
                    )}
                    <figcaption>What you gave it</figcaption>
                  </figure>
                  <span className="rtp__pair-join" aria-hidden="true" />
                  <figure className="rtp__panel">
                    {reparsedSvg ? (
                      <img src={reparsedSvg} alt="The structure OPSIN re-parsed from the name" />
                    ) : (
                      <span className="rtp__panel-empty" aria-hidden="true" />
                    )}
                    <figcaption>What the name gives back</figcaption>
                  </figure>
                </div>
              </li>
            )}

            {/* 5 — the verdict, landing last */}
            <li className="rtp__step rtp__step--verdict">
              {phase === 'ready' && (
                <>
                  {/* Through STATE_CLASS, which statuses.js exports precisely so the
                      API's underscored values (`best_effort`) and the CSS's
                      hyphenated ones (`--best-effort`) cannot drift apart. */}
                  <span className={`rtp__tier rtp__tier--${STATE_CLASS[row.status] || row.status}`}>
                    {stateLabel || 'No name'}
                  </span>
                  <p className="rtp__verdict">{verdict}</p>
                </>
              )}
            </li>
          </ol>
        )}
      </div>

      {/* The rotation control doubles as the honest index: four molecules, and
          the reader can see there are four and pick the awkward one. */}
      <div className="rtp__picker" role="group" aria-label="Choose a molecule">
        {MOLECULES.map((m, i) => (
          <button
            key={m.key}
            type="button"
            className={i === index ? 'rtp__pick rtp__pick--on' : 'rtp__pick'}
            aria-current={i === index}
            onClick={() => show(i)}
          >
            {m.label}
          </button>
        ))}
      </div>
    </section>
  )
}
