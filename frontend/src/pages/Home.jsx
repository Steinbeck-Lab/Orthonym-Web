import { useEffect, useRef, useState } from 'react'
import ExampleChips from '../components/ExampleChips'
import SamplerGrid from '../components/SamplerGrid'
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

    translateBatch(lines)
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

  return (
    <>
      <header className="site-header page-shell">
        <h1 className="site-header__title">Orthonym</h1>
        <p className="site-header__tagline">
          A SMILES <span aria-hidden="true">&rarr;</span> IUPAC name translator built on a{' '}
          <strong>deterministic, rule-based naming engine</strong> &mdash; not a language model.
        </p>
      </header>

      <main className="layout page-shell">
        <section className="input-panel" aria-label="Translate a SMILES string">
          <form onSubmit={handleSubmit} noValidate>
            <div className="input-panel__grid">
              <div className="input-panel__field">
                <label htmlFor="smiles-input" className="input-panel__label">
                  SMILES, one per line
                  <span className="input-panel__label-note"> &mdash; up to 50</span>
                </label>
                <textarea
                  id="smiles-input"
                  className="input-panel__textarea"
                  rows={6}
                  spellCheck={false}
                  autoCorrect="off"
                  autoCapitalize="off"
                  placeholder={'CCO\nC[C@H](O)CC\nCC(C)(C)C1=CC2=C(C=C1)...'}
                  value={smilesText}
                  onChange={(event) => setSmilesText(event.target.value)}
                />
                <div className="input-panel__actions">
                  <button type="submit" className="translate-button" disabled={isSubmitting}>
                    {isSubmitting ? 'Translating…' : 'Translate'}
                  </button>
                  {validationNote && (
                    <p className="input-panel__note" role="status">
                      {validationNote}
                    </p>
                  )}
                </div>
              </div>

              <aside className="disclaimer" aria-label="Accuracy disclaimer">
                <p className="disclaimer__lead">
                  Orthonym&rsquo;s naming engine is alpha-stage and rule-based &mdash; the same
                  input always gives the same output, and it will tell you when it isn&rsquo;t
                  sure.
                </p>
                <p className="disclaimer__body">
                  Measured round-trip accuracy: <strong>~30.4% overall</strong> (ChEBI 29.6%,
                  PubChem 16.9%), rising to <strong>~92.2%</strong> on its own OPSIN self-test
                  corpus. A lower-confidence name is always shown as such, never hidden; when it
                  can&rsquo;t confidently name a molecule, it abstains instead of guessing.
                </p>
              </aside>
            </div>

            <ExampleChips
              examples={examples}
              error={examplesError}
              disabled={isSubmitting}
              onPick={handleExamplePick}
            />
          </form>
        </section>

        <section className="results" aria-label="Translation results">
          {fetchError && (
            <p className="fetch-error" role="alert">
              Could not reach Orthonym&rsquo;s backend ({fetchError}). Is it running on{' '}
              <code>localhost:8000</code>?
            </p>
          )}

          <SamplerGrid rows={rows} reduceMotion={reduceMotion} />
        </section>
      </main>
    </>
  )
}

export default Home
