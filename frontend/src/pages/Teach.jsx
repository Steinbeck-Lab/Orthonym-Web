import { useEffect, useRef, useState } from 'react'
import { explainMolecule } from '../lib/api'
import './Teach.css'

// The vendored standalone Ketcher app posts window.parent a single
// {eventType: "init"} message once its structure service has actually
// finished initialising. That fires LATER than the iframe's own `load`
// event, which only means the HTML shell downloaded. Listening for this
// message is the real "editor is interactive" signal; a bare onLoad
// handler races the startup and can grab `contentWindow.ketcher` before it
// exists. Same pattern as StructureToIupac.jsx, deliberately duplicated
// rather than abstracted -- the two pages will diverge.
const READY_TIMEOUT_MS = 20000

function Teach() {
  const iframeRef = useRef(null)
  const [editorState, setEditorState] = useState('loading') // loading | ready | error
  const [phase, setPhase] = useState('idle') // idle | working | done | failed
  const [data, setData] = useState(null)
  const [note, setNote] = useState(null)

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

  function handleFrameLoad() {
    // Fast networks and warm caches can beat our listener into place.
    if (iframeRef.current?.contentWindow?.ketcher) {
      setEditorState('ready')
    }
  }

  async function handleName() {
    if (phase === 'working') return
    setNote(null)
    const ketcher = iframeRef.current?.contentWindow?.ketcher
    if (!ketcher) {
      setNote('The drawing area is still starting up. Give it a moment and try again.')
      return
    }
    let structure = ''
    try {
      structure = (await ketcher.getSmiles()) || ''
    } catch {
      setNote('Could not read your drawing. Try drawing it again.')
      return
    }
    structure = structure.trim()
    if (!structure) {
      setNote('Draw a molecule first, then press Name it.')
      return
    }
    setPhase('working')
    try {
      const result = await explainMolecule(structure)
      setData(result)
      setPhase(result.name ? 'done' : 'failed')
    } catch {
      setNote('Could not reach the naming service. Check it is running and try again.')
      setPhase('idle')
    }
  }

  return (
    <div className="teach">
      <h1 className="teach__title">Draw a molecule, learn its name</h1>
      <p className="teach__lede">
        Draw a structure below and press <strong>Name it</strong>. You will get the
        name, and you can point at any part of the name to see which atoms it
        describes.
      </p>

      <section className="teach__draw">
        {editorState === 'error' ? (
          <p className="teach__editor-error" role="alert">
            The drawing area did not load. Reload the page to try again.
          </p>
        ) : (
          <iframe
            ref={iframeRef}
            title="Molecule drawing area"
            className="teach__editor"
            src="/standalone/index.html"
            onLoad={handleFrameLoad}
          />
        )}
        <button
          type="button"
          className="teach__button"
          onClick={handleName}
          disabled={editorState !== 'ready' || phase === 'working'}
        >
          {phase === 'working' ? 'Working…' : 'Name it'}
        </button>
        {note && (
          <p className="teach__note" role="status">
            {note}
          </p>
        )}
      </section>
    </div>
  )
}

export default Teach
