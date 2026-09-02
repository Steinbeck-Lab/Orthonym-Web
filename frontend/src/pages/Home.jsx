import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import ExampleChips from '../components/ExampleChips'
import SamplerGrid from '../components/SamplerGrid'
import ConfidenceLegend from '../components/ConfidenceLegend'
import Switch from '../components/Switch'
import { fetchExamples, translateBatch, TranslateJobQueuedError } from '../lib/api'
import { MAX_ROWS, parseSmilesLines } from '../lib/parseSmiles'
import useReducedMotion from '../lib/useReducedMotion'
import './Home.css'

function emptyRow(smiles) {
  return {
    smiles,
    phase: 'pending',
    status: null,
    name: null,
    tier: null,
    formula: null,
    limit_code: null,
    error: null,
    depiction_svg: null,
    roundtrip_smiles: null,
    roundtrip_match: null,
  }
}

// WebGPU flare states: 'off' (unsupported, refused, or reduced motion -- no
// canvas in the DOM at all), 'pending' (canvas mounted, GPU still starting),
// 'live' (drawing). 'off' is also where a failure lands, so a broken driver
// degrades to the plain wordmark instead of an empty box.
function useWordmarkFlare(reduceMotion) {
  const canvasRef = useRef(null)
  const wordmarkRef = useRef(null)
  // Three pieces of state, deliberately not one: `mounted` decides whether the
  // canvas exists, and it is the ONLY thing the renderer effect may depend on.
  // `live` and `failed` are results, and they must never re-run that effect --
  // an earlier version kept a single 'off' | 'pending' | 'live' state and put
  // it in the dependency array, so setting 'live' re-ran the effect, whose
  // cleanup disposed the renderer it had just finished starting. It drew
  // exactly one frame and then sat there, empty, with no error anywhere.
  const [mounted, setMounted] = useState(false)
  const [live, setLive] = useState(false)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    // Reduced motion is a refusal, not a downgrade: this thing is a moving
    // light and there is no still version of it worth drawing.
    setMounted(!reduceMotion && typeof navigator !== 'undefined' && 'gpu' in navigator)
  }, [reduceMotion])

  useEffect(() => {
    if (!mounted) return
    const canvas = canvasRef.current
    const wordmark = wordmarkRef.current
    if (!canvas || !wordmark) return

    let cancelled = false
    let renderer
    // Imported here, not at module scope: vgpu is the single heaviest thing
    // this app can load (a 180 kB chunk), and a visitor without WebGPU must
    // never pay for it.
    import('../lib/flare/renderer')
      .then(({ createRenderer }) => {
        if (cancelled) return undefined
        renderer = createRenderer({ canvas, wordmark })
        return renderer.ready
      })
      .then(() => {
        if (!cancelled) setLive(true)
      })
      .catch((error) => {
        // An adapter that refuses, a driver that dies, a shader that will not
        // compile: all of it ends here, and the page keeps working.
        if (import.meta.env.DEV) console.warn('flare unavailable:', error)
        if (!cancelled) {
          setFailed(true)
          setLive(false)
        }
      })

    return () => {
      cancelled = true
      renderer?.dispose()
    }
  }, [mounted])

  const flare = failed || !mounted ? 'off' : live ? 'live' : 'pending'
  return { flare, flareCanvasRef: canvasRef, wordmarkRef }
}

function Home() {
  const [smilesText, setSmilesText] = useState('')
  const [examples, setExamples] = useState([])
  const [examplesError, setExamplesError] = useState(null)
  const [rows, setRows] = useState([])
  const [isSubmitting, setIsSubmitting] = useState(false)
  // Best-effort mode. Defaults ON, which is the behaviour STITCH has always
  // shipped: a molecule the strict namer abstains on gets retried against
  // the escalated one. Turning it off makes the engine strict — it can then
  // only ever return a verified name or an honest abstain.
  const [bestEffort, setBestEffort] = useState(true)
  const [validationNote, setValidationNote] = useState(null)
  const [fetchError, setFetchError] = useState(null)
  const reduceMotion = useReducedMotion()
  const { flare, flareCanvasRef, wordmarkRef } = useWordmarkFlare(reduceMotion)

  const timersRef = useRef([])

  useEffect(() => {
    let cancelled = false
    fetchExamples()
      .then((data) => {
        if (!cancelled) setExamples(data)
      })
      .catch((err) => {
        if (!cancelled) setExamplesError(err?.message || 'network error')
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    return () => clearTimers()
  }, [])

  function clearTimers() {
    timersRef.current.forEach((id) => clearTimeout(id))
    timersRef.current = []
  }

  // Reveals settle per SMILES row (the batch "chase"), and within a row
  // StitchedName animates per character. The direction's STORY promises
  // "rule-by-rule" reveal, but the /api/translate contract (see lib/api.js)
  // returns only a finished name per row, not its rule-firing/fragment
  // boundaries — OpenSTOUT's name_tiered() doesn't expose that granularity
  // today. Per-character is the honest stand-in for "assembled piece by
  // piece" until a fragment-level API exists to reveal true rule order.
  function runTranslate(lines) {
    clearTimers()
    setFetchError(null)
    setRows(lines.map(emptyRow))
    setIsSubmitting(true)

    translateBatch(lines, { bestEffort })
      .then((results) => {
        setIsSubmitting(false)

        if (reduceMotion) {
          setRows(results.map((result) => ({ ...result, phase: 'done' })))
          return
        }

        let i = 0
        const revealNext = () => {
          if (i >= results.length) return
          const current = i
          setRows((prev) =>
            prev.map((row, idx) =>
              idx === current ? { ...results[current], phase: 'active' } : row,
            ),
          )
          const nameLength = results[current]?.name?.length ?? 0
          const chaseDuration = Math.min(1100, 380 + nameLength * 32)

          const settleTimer = setTimeout(() => {
            setRows((prev) =>
              prev.map((row, idx) => (idx === current ? { ...row, phase: 'done' } : row)),
            )
          }, chaseDuration)
          timersRef.current.push(settleTimer)

          i += 1
          const nextTimer = setTimeout(revealNext, chaseDuration + 90)
          timersRef.current.push(nextTimer)
        }
        revealNext()
      })
      .catch((err) => {
        setIsSubmitting(false)
        if (err instanceof TranslateJobQueuedError) {
          // Not a failure -- real work is running on the server, just too
          // large or slow for the synchronous fast path. STITCH has no
          // batch-job polling UI (a separate, larger project), so the
          // honest thing is to say that plainly rather than render an
          // empty grid, which used to look identical to zero results.
          setRows([])
          setValidationNote(
            `This batch (${err.moleculeCount} molecules) is running as a background job on ` +
              'the server instead of returning immediately. This page cannot track a queued ' +
              "job's progress — try a smaller batch for an immediate result."
          )
          return
        }
        setFetchError(err?.message || 'unknown network error')
        setRows([])
      })
  }

  function handleSubmit(event) {
    event.preventDefault()
    if (isSubmitting) return

    const { lines, total, truncated } = parseSmilesLines(smilesText)
    if (!lines.length) {
      setValidationNote('Enter at least one SMILES string (one per line) before translating.')
      return
    }
    setValidationNote(
      truncated ? `Only the first ${MAX_ROWS} of ${total} lines will be processed.` : null,
    )
    runTranslate(lines)
  }

  function handleExamplePick(example) {
    if (isSubmitting) return
    setSmilesText(example.smiles)
    setValidationNote(null)
    runTranslate([example.smiles])
  }

  const hasResults = rows.length > 0

  return (
    <>
      {/* The hero. It carried a title and a four-line lede until 2026-09-02,
          when the owner replaced both with the wordmark and had the lede
          dropped outright (that copy still lives on About).
          The light is the real thing: vgpu's nextjs-flare (vercel-labs/vgpu,
          MIT), vendored into src/lib/flare and pointed at STITCH's own
          wordmark -- a 48-step ray walk jittered by blue noise over a
          separable blur chain, raking light along the letter OUTLINES the way
          Next's "N" is lit. Not a glow in the middle of the card; the
          wordmark is the light source.
          It only runs where WebGPU exists and motion is welcome. Everywhere
          else the wordmark simply keeps its crimson text-shadow halo, which
          is why there is no canvas in the markup until we know. */}
      <section className="home-hero page-shell" aria-label="Introduction">
        {flare !== 'off' && (
          <canvas
            className="home-hero__flare"
            ref={flareCanvasRef}
            aria-hidden="true"
          />
        )}

        {/* When the flare is live it draws these letters itself, lit. The
            heading stays in the DOM at the same size -- it is what the flare
            is measured against, and what a screen reader and a crawler read
            -- but its ink goes transparent so the two do not double up. */}
        <h1
          className={
            flare === 'live' ? 'home-hero__word home-hero__word--lit' : 'home-hero__word'
          }
          ref={wordmarkRef}
        >
          Stitch
        </h1>

        {/* The bold letters spell STITCH: S-T-I-T-C-H. "Ch" keeps the word's
            real spelling rather than shouting CH to force the acronym --
            the pattern still reads. Each one glows crimson under the
            pointer, which is the whole reason they are marked at all. */}
        <p className="home-hero__tagline">
          <b className="home-hero__cap">S</b>MILES <b className="home-hero__cap">T</b>o{' '}
          <b className="home-hero__cap">I</b>UPAC name{' '}
          <b className="home-hero__cap">T</b>ranslator for{' '}
          <b className="home-hero__cap">Ch</b>emistry
        </p>
      </section>

      <main className="workbench" aria-label="Translate SMILES to IUPAC names">
        {fetchError && (
          <p className="workbench__alert" role="alert">
            Could not reach STITCH&rsquo;s backend ({fetchError}). Is it running on{' '}
            <code>localhost:8000</code>?
          </p>
        )}

        <section className="workbench__input" aria-label="Translate a SMILES string">
          <form onSubmit={handleSubmit} noValidate>
            <div className="field">
              <label htmlFor="smiles-input" className="field__label">
                SMILES &mdash; one per line, up to {MAX_ROWS}
              </label>
              <textarea
                id="smiles-input"
                className="field__control"
                rows={8}
                spellCheck={false}
                autoCorrect="off"
                autoCapitalize="off"
                placeholder={'CCO\nC[C@H](O)CC\nCC(C)(C)C1=CC2=C(C=C1)...'}
                value={smilesText}
                onChange={(event) => setSmilesText(event.target.value)}
              />
            </div>

            <Switch
              id="best-effort-mode"
              checked={bestEffort}
              onChange={setBestEffort}
              disabled={isSubmitting}
              label="Best-effort mode"
              onWord="On"
              offWord="Off"
              hint={
                bestEffort
                  ? 'A molecule the strict rules cannot name is retried with a looser pass. That can return a real name OPSIN could not confirm — always marked as unverified, never as a PIN.'
                  : 'Strict. Only names the engine can verify are shown; anything else comes back as an honest abstain rather than an unverified guess.'
              }
            />

            <div className="workbench__actions">
              <button type="submit" className="btn btn--accent" disabled={isSubmitting}>
                {isSubmitting ? 'Translating…' : 'Translate'}
              </button>
              {validationNote && (
                <p className="workbench__note" role="status">
                  {validationNote}
                </p>
              )}
            </div>

            <ExampleChips
              examples={examples}
              error={examplesError}
              disabled={isSubmitting}
              onPick={handleExamplePick}
            />
          </form>

          <p className="page-about-note workbench__about">
            Read how this works, and STITCH&rsquo;s measured accuracy, on the{' '}
            <Link to="/about" className="about-link">
              About
            </Link>{' '}
            page.
          </p>
        </section>

        {hasResults ? (
          <SamplerGrid rows={rows} reduceMotion={reduceMotion} />
        ) : (
          <ConfidenceLegend />
        )}
      </main>

    </>
  )
}

export default Home
