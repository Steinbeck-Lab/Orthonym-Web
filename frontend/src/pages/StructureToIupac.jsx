import { useEffect, useRef, useState } from 'react'
import SamplerGrid from '../components/SamplerGrid'
import { translateBatch } from '../lib/api'
import useReducedMotion from '../lib/useReducedMotion'
import './StructureToIupac.css'

// The bundled standalone Ketcher app posts window.parent a single
// {eventType: "init"} message once its structure service has actually
// finished initializing (see standalone/static/js/main.*.js, the
// onInit callback passed to Ketcher.create) -- this fires meaningfully
// later than the iframe's own `load` event, which only means the HTML
// shell downloaded. Listening for this message is the real "editor is
// interactive" signal; a bare onLoad handler races the WASM/service
// startup and can grab `contentWindow.ketcher` before it exists.
const READY_TIMEOUT_MS = 20000

const EMPTY_SAMPLER_MESSAGE =
  "Nothing drawn yet. Sketch a structure above, then press Translate and it will be stitched in below."

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
  const iframeRef = useRef(null)
  const timersRef = useRef([])
  const [editorState, setEditorState] = useState('loading') // 'loading' | 'ready' | 'error'
  const [rows, setRows] = useState([])
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [note, setNote] = useState(null)
  const [fetchError, setFetchError] = useState(null)
  const reduceMotion = useReducedMotion()

  useEffect(() => {
    function handleMessage(event) {
      if (event.data && event.data.eventType === 'init') {
        setEditorState('ready')
      }
    }
    window.addEventListener('message', handleMessage)

    const timeoutId = setTimeout(() => {
      setEditorState((current) => (current === 'loading' ? 'error' : current))
    }, READY_TIMEOUT_MS)

    return () => {
      window.removeEventListener('message', handleMessage)
      clearTimeout(timeoutId)
    }
  }, [])

  useEffect(() => {
    return () => clearTimers()
  }, [])

  function clearTimers() {
    timersRef.current.forEach((id) => clearTimeout(id))
    timersRef.current = []
  }

  function handleFrameLoad() {
    // Belt-and-suspenders: if `ketcher` is already attached by the time
    // the iframe's load event fires (fast networks/warm caches can beat
    // our message listener into place), don't wait on the postMessage.
    if (iframeRef.current?.contentWindow?.ketcher) {
      setEditorState('ready')
    }
  }

  function handleFrameError() {
    setEditorState('error')
  }

  async function handleTranslate() {
    if (isSubmitting) return
    setNote(null)

    const ketcher = iframeRef.current?.contentWindow?.ketcher
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
    <section className="structure-page page-shell" aria-label="Structure to IUPAC">
      <h1 className="structure-page__title">Structure &rarr; IUPAC</h1>
      <p className="structure-page__tagline">
        Draw a molecule and STITCH will translate it with the exact same{' '}
        <strong>deterministic, rule-based naming engine</strong> the Translate page uses.
      </p>

      <div className="structure-page__layout">
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
              className="translate-button"
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
        </section>

        <aside className="structure-page__aside" aria-label="How this works">
          <p className="structure-page__aside-lead">
            Draw a molecule, then press Translate &mdash; the drawn structure is read straight
            out of the editor as a SMILES string and sent to the same engine behind the Translate
            page.
          </p>
          <p className="structure-page__aside-body">
            The result lands in the same sampler tile you&rsquo;d see there: a solid stitched
            fill means a confirmed Preferred IUPAC Name (PIN), a dashed name is a lower-confidence
            but round-trip&ndash;verified fallback, a faint thread-colored outline means a name
            the engine could produce but not verify, and bare weave means it honestly
            couldn&rsquo;t name it at all.
          </p>
        </aside>
      </div>

      <section className="results" aria-label="Translation result">
        {fetchError && (
          <p className="fetch-error" role="alert">
            Could not reach STITCH&rsquo;s backend ({fetchError}). Is it running on{' '}
            <code>localhost:8000</code>?
          </p>
        )}

        <SamplerGrid rows={rows} reduceMotion={reduceMotion} emptyMessage={EMPTY_SAMPLER_MESSAGE} />
      </section>
    </section>
  )
}

export default StructureToIupac
