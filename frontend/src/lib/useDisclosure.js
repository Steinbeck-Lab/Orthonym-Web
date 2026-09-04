import { useEffect, useId, useRef, useState } from 'react'

/**
 * The disclosure mechanism behind the notch-and-drawer chrome that
 * OpsinNote.jsx and ConfidenceLegend.jsx both wear (`.info`, `.info__notch`,
 * `.info__drawer`... all promoted to App.css on 2026-09-04 for exactly this
 * reuse): open/seen state, the panel id, the Escape-and-outside-click
 * effect, and the class-array assembly. The CSS was shared by promotion;
 * this is the same move for the ~25-30 lines of JS that were near-verbatim
 * in both components.
 *
 * Each caller keeps its own notch label and drawer content, and anything
 * that is not part of the mechanism itself. ConfidenceLegend's `openToSide`
 * class and its `onOpenChange` reporting effect are genuinely Home-only
 * wiring and stay in that component rather than moving here.
 */
export function useDisclosure() {
  const [open, setOpen] = useState(false)
  // The bulb breathes until the drawer has been opened once, then goes
  // steady for the rest of the session -- a lamp that keeps pulsing at
  // someone who has already read the thing is a nervous tic, not a signal.
  const [seen, setSeen] = useState(false)
  const panelId = useId()
  const rootRef = useRef(null)

  // Escape closes it, and so does a click anywhere else -- bound only while
  // OPEN, so the closed state costs no listeners.
  useEffect(() => {
    if (!open) return undefined
    const onKeyDown = (event) => {
      if (event.key === 'Escape') setOpen(false)
    }
    const onPointerDown = (event) => {
      if (!rootRef.current?.contains(event.target)) setOpen(false)
    }
    document.addEventListener('keydown', onKeyDown)
    document.addEventListener('pointerdown', onPointerDown)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      document.removeEventListener('pointerdown', onPointerDown)
    }
  }, [open])

  function toggle() {
    setOpen((was) => !was)
    setSeen(true)
  }

  const classes = ['info']
  if (open) classes.push('info--open')
  if (!seen) classes.push('info--unseen')

  return { open, setOpen, panelId, rootRef, toggle, classes }
}
