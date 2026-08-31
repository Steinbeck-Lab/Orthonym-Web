import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import ExampleChips from '../components/ExampleChips'
import SamplerGrid from '../components/SamplerGrid'
import ConfidenceLegend from '../components/ConfidenceLegend'
import Switch from '../components/Switch'
import { fetchExamples, translateBatch } from '../lib/api'
import { parseSmilesLines } from '../lib/parseSmiles'
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

function Home() {
  const [smilesText, setSmilesText] = useState('')
  const [examples, setExamples] = useState([])
  const [examplesError, setExamplesError] = useState(null)
  const [rows, setRows] = useState([])
  const [isSubmitting, setIsSubmitting] = useState(false)
  // Best-effort mode. Defaults ON, which is the behaviour Orthonym has always
  // shipped: a molecule the strict namer abstains on gets retried against
  // the escalated one. Turning it off makes the engine strict — it can then
  // only ever return a verified name or an honest abstain.
  const [bestEffort, setBestEffort] = useState(true)
  const [validationNote, setValidationNote] = useState(null)
  const [fetchError, setFetchError] = useState(null)
  const reduceMotion = useReducedMotion()

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
  // ThreadedName animates per character. The direction's STORY promises
  // "rule-by-rule" reveal, but the /api/translate contract (see lib/api.js)
  // returns only a finished name per row, not its rule-firing/fragment
  // boundaries — Orthonym's name_tiered() doesn't expose that granularity
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
      truncated ? `Only the first 50 of ${total} lines will be processed.` : null,
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
      <section className="home-hero page-shell" aria-label="Introduction">
        <h1 className="home-hero__title">A name you can check</h1>
        <p className="home-hero__lede">
          Orthonym translates SMILES into IUPAC names with a deterministic, rule-based engine
          &mdash; not a language model. Every result carries the rule that earned it, so you can
          see whether it is a verified Preferred IUPAC Name, a verified fallback, an unverified
          best effort, or an honest refusal.
        </p>
      </section>

      <main className="workbench" aria-label="Translate SMILES to IUPAC names">
        {fetchError && (
          <p className="workbench__alert" role="alert">
            Could not reach Orthonym&rsquo;s backend ({fetchError}). Is it running on{' '}
            <code>localhost:8000</code>?
          </p>
        )}

        <section className="workbench__input" aria-label="Translate a SMILES string">
          <form onSubmit={handleSubmit} noValidate>
            <div className="field">
              <label htmlFor="smiles-input" className="field__label">
                SMILES &mdash; one per line, up to 50
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
            Read how this works, and Orthonym&rsquo;s measured accuracy, on the{' '}
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

      {/* The accuracy band, on the page where people submit molecules rather
          than only on About. One edge-to-edge bento: an intro cell welded to
          the three figures, so the width carries real content instead of a
          void. These are Orthonym v1.0.0's published figures (its README
          § Accuracy), the same ones About cites — never rounded up, and never
          split per-corpus, because v1.0.0 publishes no per-corpus breakdown. */}
      <section className="home-accuracy" aria-label="Measured accuracy">
        <div className="home-accuracy__intro">
          <h2 className="home-accuracy__title">How accurate is it?</h2>
          <p className="home-accuracy__note">
            Deterministic, so the same input always gives the same output. Its stated priority is
            never to emit a name for the wrong molecule &mdash; a refusal counts as a failure
            here, so the figure is not flattered by abstentions.
          </p>
          <p className="home-accuracy__source">
            Orthonym v1.0.0 &middot; 1,500-molecule round-trip benchmark (ChEBI + PubChem)
          </p>
        </div>
        <div className="home-accuracy__stats">
          <div className="home-accuracy__cell">
            <span className="spec__value">94.8%</span>
            <span className="spec__label">Round-trip exact match</span>
          </div>
          <div className="home-accuracy__cell">
            <span className="spec__value">0</span>
            <span className="spec__label">Wrong structures emitted</span>
          </div>
          <div className="home-accuracy__cell">
            <span className="spec__value">1,500</span>
            <span className="spec__label">Molecules benchmarked</span>
          </div>
        </div>
      </section>
    </>
  )
}

export default Home
