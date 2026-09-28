import { useCallback, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import BuddyDrawing from './BuddyDrawing'
import useReducedMotion from '../lib/useReducedMotion'

// Kekunyo, the buddy, loose on the About page (owner request 2026-09-28): every so
// often it does one small thing and leaves -- peeks in from the right edge,
// runs along the bottom, pops up from below the screen, or appears in a
// sparkle and vanishes again. Never twice the same act in a row, and never on
// the left edge, where the issue tab lives.
//
// It only ever moves along the edges of the window, so it passes over text
// for a moment at most. Every act is slow, 7 to 12 seconds, and the gaps
// between acts are longer still. Moving content that starts on its own needs a way to
// stop it (WCAG 2.2.2): clicking the buddy, or pressing Escape, sends it away
// for the rest of the visit. It never appears with reduced motion on, below
// 960px (where the edges ARE the page), or while the tab is hidden.
//
// Decorative, so aria-hidden: the acts carry no information. Rendered into
// <body> through a portal, so its coming and going never touches the page's
// own layout (`* + *` spacing rules count every child, fixed or not).

const ACTS = ['peek', 'run', 'pop', 'vanish']
const WIDE = '(min-width: 960px)'

const between = (lo, hi) => lo + Math.random() * (hi - lo)

function nextAct(last) {
  const options = ACTS.filter((act) => act !== last)
  return options[Math.floor(Math.random() * options.length)]
}

export default function BuddyRoam() {
  const reduceMotion = useReducedMotion()
  const [scene, setScene] = useState(null)
  const [stopped, setStopped] = useState(false)
  const timer = useRef(null)
  const last = useRef(null)

  const schedule = useCallback((delay) => {
    clearTimeout(timer.current)
    timer.current = setTimeout(() => {
      if (document.hidden || !window.matchMedia(WIDE).matches) {
        schedule(4000)
        return
      }
      const act = nextAct(last.current)
      last.current = act
      setScene({
        act,
        key: Date.now(),
        x: between(14, 78),
        y: between(24, 64),
        dir: Math.random() < 0.5 ? 'ltr' : 'rtl',
      })
    }, delay)
  }, [])

  useEffect(() => {
    if (reduceMotion || stopped) return undefined
    schedule(between(4000, 7000))
    return () => clearTimeout(timer.current)
  }, [reduceMotion, stopped, schedule])

  const goAway = useCallback(() => {
    clearTimeout(timer.current)
    setScene((current) => (current ? { ...current, leaving: true } : null))
    setStopped(true)
  }, [])

  useEffect(() => {
    if (stopped) return undefined
    const onKey = (event) => {
      if (event.key === 'Escape') goAway()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [stopped, goAway])

  // The act's own animation ends it, or the goodbye when it was sent away.
  // The parts' own animations (ib-*) bubble up here too and are ignored.
  const onAnimationEnd = (event) => {
    if (!event.animationName.startsWith('roam-')) return
    setScene(null)
    if (!stopped) schedule(between(9000, 18000))
  }

  if (reduceMotion || !scene) return null
  return createPortal(
    <div
      key={scene.key}
      className={`buddy-roam buddy-roam--${scene.act} buddy-roam--${scene.dir}${scene.leaving ? ' buddy-roam--leaving' : ''}`}
      style={{ '--x': `${scene.x}vw`, '--y': `${scene.y}vh` }}
      onAnimationEnd={onAnimationEnd}
      onClick={goAway}
      aria-hidden="true"
    >
      {/* The act moves the outer box; the goodbye shrinks this one, so it
          can leave from wherever the act has carried it. */}
      <span className="buddy-roam__inner">
        <BuddyDrawing />
      </span>
    </div>,
    document.body,
  )
}
