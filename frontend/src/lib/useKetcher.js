import { useEffect, useRef, useState } from 'react'

// The bundled standalone Ketcher app posts window.parent a single
// {eventType: "init"} message once its structure service has actually
// finished initializing (see standalone/static/js/main.*.js, the onInit
// callback passed to Ketcher.create) -- this fires meaningfully later than
// the iframe's own `load` event, which only means the HTML shell downloaded.
// Listening for this message is the real "editor is interactive" signal; a
// bare onLoad handler races the WASM/service startup and can grab
// `contentWindow.ketcher` before it exists.
const READY_TIMEOUT_MS = 20000

/**
 * Owns the startup handshake for the bundled Ketcher structure editor,
 * embedded via <iframe src="/standalone/index.html">. Shared by
 * StructureToIupac.jsx and Teach.jsx, which were independently duplicating
 * this handshake (state machine, message listener, timeout, belt-and-
 * suspenders check) with only comment wording differing between them.
 *
 * Usage: spread the returned `iframeRef`/`handleFrameLoad`/`handleFrameError`
 * onto the <iframe>, drive loading/error UI off `editorState`, and call
 * `getKetcher()` when the page needs the live editor instance (e.g. on a
 * "Translate"/"Name it" button click) -- it returns null/undefined if the
 * editor is not actually ready yet, which each page reports in its own words.
 */
export function useKetcher({ enabled = true } = {}) {
  const iframeRef = useRef(null)
  const [editorState, setEditorState] = useState('loading') // 'loading' | 'ready' | 'error'

  // `enabled` gates the readiness clock, and it exists because the merged
  // /explain page mounts the iframe only when the Draw tab is chosen. Armed
  // unconditionally, the 20 s timeout starts when the PAGE mounts, so anyone
  // who picks Draw more than 20 s after arriving finds the editor already
  // declared broken -- with no iframe having ever existed to break. Seen in a
  // real browser, not reasoned about: the panel read "The drawing area did
  // not load" while /standalone/index.html was serving 200.
  //
  // Defaults true so a caller that always renders the iframe needs no change.
  useEffect(() => {
    if (!enabled) {
      // Back to 'loading' so re-entering the tab starts a fresh handshake
      // rather than inheriting a verdict from a previous visit.
      setEditorState('loading')
      return undefined
    }

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
  }, [enabled])

  function handleFrameLoad() {
    // Belt-and-suspenders: if `ketcher` is already attached by the time the
    // iframe's load event fires (fast networks/warm caches can beat our
    // message listener into place), don't wait on the postMessage.
    if (iframeRef.current?.contentWindow?.ketcher) {
      setEditorState('ready')
    }
  }

  function handleFrameError() {
    setEditorState('error')
  }

  function getKetcher() {
    return iframeRef.current?.contentWindow?.ketcher
  }

  return { iframeRef, editorState, handleFrameLoad, handleFrameError, getKetcher }
}

export default useKetcher
