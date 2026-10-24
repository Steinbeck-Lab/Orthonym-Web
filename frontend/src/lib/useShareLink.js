import { useEffect, useRef } from 'react'
import { readShareHash } from './shareLink'

/** Calls `onFields` with a share link's fields (lib/shareLink.js) once, on
 *  arrival, when the page was opened from one. A link is read when the page
 *  opens and never again; the ref stops StrictMode's second mount from
 *  running it twice. */
export default function useShareLink(onFields) {
  const done = useRef(false)
  useEffect(() => {
    if (done.current) return
    done.current = true
    const fields = readShareHash(window.location.hash)
    if (fields) onFields(fields)
    // oxlint-disable-next-line react-hooks/exhaustive-deps
  }, [])
}
