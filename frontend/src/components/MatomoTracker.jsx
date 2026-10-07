import { useEffect, useRef } from 'react'
import { useLocation } from 'react-router-dom'
import { MATOMO, pageUrl, pageViewCommands, setupCommands } from '../lib/matomo'

// Counts one page view per route the visitor lands on (lib/matomo.js says what
// is and is not sent). Renders nothing.
//
// This is a single-page app, so Matomo's own snippet would count the first
// page and never another: route changes are pushState, not page loads. The
// effect re-runs on every path change instead.
//
// The setTimeout is what keeps redirects honest. The catch-all and the old
// routes are <Navigate>s, so /structure renders once and then becomes
// /explain?input=draw in the same tick; the redirect's re-render cancels the
// first timer, and only the address the visitor ends up on is counted.
function MatomoTracker() {
  const { pathname } = useLocation()
  const last = useRef(null)

  useEffect(() => {
    if (!MATOMO) return undefined
    const timer = setTimeout(() => {
      const url = pageUrl(window.location)
      if (url === last.current) return
      const paq = (window._paq = window._paq || [])
      if (last.current === null) {
        paq.push(...setupCommands(MATOMO))
        const script = document.createElement('script')
        script.async = true
        script.src = `${MATOMO.url}matomo.js`
        document.head.append(script)
      }
      paq.push(...pageViewCommands(url, document.title, last.current))
      last.current = url
    }, 0)
    return () => clearTimeout(timer)
  }, [pathname])

  return null
}

export default MatomoTracker
