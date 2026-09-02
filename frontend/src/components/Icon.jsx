import {
  ArrowLeft,
  ArrowRight,
  ArrowRightLeft,
  Plus,
  RefreshCw,
  Square,
  Trash2,
  Upload,
} from 'lucide-react'

// The button icons: ONE map from a semantic name to a real, drawn icon.
//
// These were hand-drawn from strokes for one commit, on the argument that
// this system builds every mark it owns out of rules -- the confidence
// specimens, the footer's join, the nav's arriving dot, the drop zone's
// seam. That argument holds for the marks that CARRY MEANING and are drawn
// large. It does not survive a 14px button icon: a two-atom bond turning
// into a line of type is a legible figure at 40px and an illegible squiggle
// at 14, which is what shipped and what the owner correctly rejected.
//
// So: lucide-react. It is stroke-based at a 24-unit grid, which is the same
// language, drawn properly by people who do this at 14px for a living. The
// icons the owner's own pinned references use (21st.dev, uselayouts) come
// from the same set.
//
// Call sites use the SEMANTIC name, never the lucide one. That indirection
// is the whole point of this file: swapping a glyph, or the whole set, is
// one line here rather than a search across five pages -- and a name like
// `translate` says what the button does, while `ArrowRightLeft` says what it
// looks like.
const ICONS = {
  translate: ArrowRightLeft, // SMILES becomes a name, and back again
  upload: Upload,
  stop: Square, // a stopped thing is a shape, not a gesture
  trash: Trash2,
  refresh: RefreshCw,
  plus: Plus,
  back: ArrowLeft,
  forward: ArrowRight,
}

/**
 * @param name  one of the keys above.
 * @param size  px. 15 suits a 44px button's mono label; 13 a smaller control.
 */
export default function Icon({ name, size = 15 }) {
  const Glyph = ICONS[name]
  // A missing name renders NOTHING rather than a placeholder: a typo should
  // cost a label its icon, never draw a mystery box beside it.
  if (!Glyph) return null
  return (
    <Glyph
      className="icon"
      size={size}
      strokeWidth={1.75}
      aria-hidden="true"
      focusable="false"
    />
  )
}
