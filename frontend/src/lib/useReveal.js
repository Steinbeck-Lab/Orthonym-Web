import { useEffect, useRef, useState } from 'react'

/**
 * Stage a section in as it reaches the viewport, once.
 *
 * The default state is REVEALED, and that is the whole safety argument: if the
 * observer never runs -- no IntersectionObserver, a script error, a crawler,
 * Reader mode -- the page is a complete, readable document rather than a
 * column of invisible sections waiting for an event that will not arrive. The
 * hook only ever hides content it has proven it can bring back, in the one
 * frame between mount and the observer's first callback.
 *
 * Returns [ref, className-suffix]. Callers spell their own class so the
 * animation stays in CSS where the reduced-motion branch already lives.
 */
export default function useReveal({ reduced = false, threshold = 0.15 } = {}) {
  const ref = useRef(null)
  const [shown, setShown] = useState(true)

  useEffect(() => {
    if (reduced) {
      setShown(true)
      return undefined
    }
    const el = ref.current
    if (!el || typeof IntersectionObserver === 'undefined') return undefined

    // Anything already on screen at mount stays visible -- no flash, and the
    // first viewport never animates, which is what stops the page feeling
    // like it is assembling itself while you read it.
    const box = el.getBoundingClientRect()
    if (box.top < window.innerHeight * 0.9) {
      setShown(true)
      return undefined
    }

    setShown(false)
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) {
          setShown(true)
          observer.disconnect()
        }
      },
      { threshold }
    )
    observer.observe(el)

    // A DEAD MAN'S SWITCH, and it is not theoretical: a full-page screenshot
    // of this very page captured three sections at opacity 0, because the tool
    // grew the viewport rather than scrolling it and the observer never fired.
    // A print job, a crawler, a headless capture or a browser that throttles
    // observers in a background tab can all reach the same state. On a page
    // whose entire job is credibility, content that stays invisible because an
    // animation did not run is the worst failure available, so after four
    // seconds the reveal happens regardless of whether anything intersected.
    const failsafe = window.setTimeout(() => {
      setShown(true)
      observer.disconnect()
    }, 4000)

    return () => {
      window.clearTimeout(failsafe)
      observer.disconnect()
    }
  }, [reduced, threshold])

  return [ref, shown]
}
