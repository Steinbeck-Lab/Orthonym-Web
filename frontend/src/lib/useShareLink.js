import { useEffect, useRef } from 'react'
import { readShareHash } from './shareLink.js'

/** Reads `win`'s share hash now and again on every `hashchange`, calling
 *  `onFields` with the fields of each one that has any. Returns the
 *  unsubscribe. Its own function so node --test can drive it with a fake
 *  window. */
export function watchShareHash(win, onFields, { initial = true } = {}) {
  const read = () => {
    const fields = readShareHash(win.location.hash)
    if (fields) onFields(fields)
  }
  if (initial) read()
  // A link pasted into a tab already on this route changes only the
  // fragment: no navigation, no remount, so the mount-time read never sees it.
  win.addEventListener('hashchange', read)
  return () => win.removeEventListener('hashchange', read)
}

/** Calls `onFields` with a share link's fields (lib/shareLink.js) on arrival,
 *  when the page was opened from one, and again whenever the fragment changes
 *  to another link. The ref stops StrictMode's second mount from reading the
 *  arrival link twice; the latest `onFields` is the one called, so a caller's
 *  inline closure sees its current state. */
export default function useShareLink(onFields) {
  const done = useRef(false)
  const latest = useRef(onFields)
  latest.current = onFields
  useEffect(() => {
    const first = !done.current
    done.current = true
    return watchShareHash(window, (fields) => latest.current(fields), { initial: first })
  }, [])
}
