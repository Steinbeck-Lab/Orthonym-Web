import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import SamplerGrid from '../components/SamplerGrid'
import { translateBatch } from '../lib/api'
import useReducedMotion from '../lib/useReducedMotion'
import { useKetcher } from '../lib/useKetcher'
import './StructureToIupac.css'

const EMPTY_SAMPLER_MESSAGE =
  "Nothing drawn yet. Sketch a structure above, then press Translate and it will be entered below."

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
  }
}

function StructureToIupac() {
  const { iframeRef, editorState, handleFrameLoad, handleFrameError, getKetcher } = useKetcher()
  const timersRef = useRef([])
  const [rows, setRows] = useState([])
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [note, setNote] = useState(null)
  const [fetchError, setFetchError] = useState(null)
  const reduceMotion = useReducedMotion()

  useEffect(() => {
    return () => clearTimers()
  }, [])

  function clearTimers() {
    timersRef.current.forEach((id) => clearTimeout(id))
    timersRef.current = []
  }

  async function handleTranslate() {
    if (isSubmitting) return
    setNote(null)

    const ketcher = getKetcher()
    if (!ketcher) {
      setNote('The structure editor is not ready yet — wait a moment and try again.')
      return
    }

    let smiles = ''
    try {
      smiles = (await ketcher.getSmiles()) || ''
    } catch {
      setNote('Could not read the drawn structure. Try redrawing it.')
      return
    }
    smiles = smiles.trim()

    if (!smiles) {
      setNote('Draw a structure in the editor above before translating.')
      return
    }

    runTranslate(smiles)
  }

  function runTranslate(smiles) {
    clearTimers()
    setFetchError(null)
    setRows([emptyRow(smiles)])
    setIsSubmitting(true)

    translateBatch([smiles])
      .then((results) => {
        setIsSubmitting(false)
        const result = results[0]

        if (!result) {
          setFetchError('no result returned for the drawn structure')
          setRows([])
          return
        }

        if (reduceMotion) {
          setRows([{ ...result, phase: 'done' }])
          return
        }

        setRows([{ ...result, phase: 'active' }])
        const nameLength = result?.name?.length ?? 0
        const chaseDuration = Math.min(1100, 380 + nameLength * 32)

        const settleTimer = setTimeout(() => {
          setRows([{ ...result, phase: 'done' }])
        }, chaseDuration)
        timersRef.current.push(settleTimer)
      })
      .catch((err) => {
        setIsSubmitting(false)
        setFetchError(err?.message || 'unknown network error')
        setRows([])
      })
  }

  return (
    <>
      <div className="page-head page-shell">
        <h1 className="page-head__title">Draw it, name it</h1>
        <p className="page-head__lede">
          Draw a molecule and STITCH translates it with the exact same deterministic, rule-based
          naming engine the Translate page uses &mdash; and reports the same honest confidence
          tier for the result.
        </p>
      </div>

      <main className="workspace workspace--draw" aria-label="Structure to IUPAC">
        <section className="editor-panel" aria-label="Draw a structure">
          <div className="editor-panel__frame-wrap">
            <iframe
              ref={iframeRef}
              className="editor-panel__frame"
              title="Chemical structure editor"
              src="/standalone/index.html"
              onLoad={handleFrameLoad}
              onError={handleFrameError}
            />

            {editorState === 'loading' && (
              <div className="editor-panel__overlay editor-panel__overlay--loading" role="status">
                <p>Loading the structure editor&hellip;</p>
              </div>
            )}

            {editorState === 'error' && (
              <div className="editor-panel__overlay editor-panel__overlay--error" role="alert">
                <p>
                  The structure editor couldn&rsquo;t load. Reload the page, or check that{' '}
                  <code>/standalone</code> is being served.
                </p>
              </div>
            )}
          </div>

          <div className="editor-panel__actions">
            <button
              type="button"
              className="btn"
              onClick={handleTranslate}
              disabled={isSubmitting || editorState !== 'ready'}
            >
              {isSubmitting ? 'Translating…' : 'Translate'}
            </button>
            {note && (
              <p className="editor-panel__note" role="status">
                {note}
              </p>
            )}
          </div>

          <p className="page-about-note">
            Read how this works, and STITCH&rsquo;s measured accuracy, on the{' '}
            <Link to="/about" className="about-link">
              About
            </Link>{' '}
            page.
          </p>
        </section>

        <section className="results" aria-label="Translation result">
          {fetchError && (
            <p className="fetch-error" role="alert">
              Could not reach STITCH&rsquo;s backend ({fetchError}). Is it running on{' '}
              <code>localhost:8000</code>?
            </p>
          )}

          <SamplerGrid rows={rows} reduceMotion={reduceMotion} emptyMessage={EMPTY_SAMPLER_MESSAGE} />
        </section>
      </main>
    </>
  )
}

export default StructureToIupac
