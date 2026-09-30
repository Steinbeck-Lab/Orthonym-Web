// What the /explain page decides to show, kept pure so it is tested on real
// responses instead of through a browser.
import { isPart, nodeById, partOf } from './nameTargets.js'

// Spec 7: a whole-request failure is ONE message and no partial result. The
// backend marks it with `error` and no drawing (an unreadable name, an engine
// that would not name the structure). An error that arrives WITH a drawing is
// the partial case (the structure was drawn, its name could not be broken
// down) and stays a result with the message beside it.
export function explainPhase(result) {
  return result?.error && !result.svg ? 'error' : 'success'
}

// What the detail panel says about a node, besides its own line.
//   partLabel     the part a notation node belongs to, else null
//   unmapped      the structure-in path could not pin it to atoms
//   nothingLights it has no atoms by design (a stereo word, a locant with no
//                 single stereocentre), which is not the same as unmapped
//   notation      it owns no atoms itself but lights its parent's
export function detailNotes(nodes, id) {
  const node = nodeById(nodes, id)
  if (!node) return { partLabel: null, nothingLights: false, notation: false, unmapped: false }
  const lit = Array.isArray(node.lights) && node.lights.length > 0
  const unmapped = Boolean(node.atoms_unmapped)
  return {
    partLabel: isPart(node) ? null : (partOf(nodes, id)?.label ?? null),
    unmapped,
    nothingLights: !lit && !unmapped,
    notation: !isPart(node) && lit && (node.owns || []).length === 0,
  }
}

// How one piece of the name is marked. Only the hovered/pinned node itself is
// 'active'; its PART (the node the spec says to mark) is 'context'. Siblings
// of the active node are not marked: hovering `2S` must not wash `1R`.
export function pieceMark(piece, activeId, activePart) {
  if (!piece.nodeId || activeId === null || activeId === undefined) return null
  if (piece.nodeId === activeId) return 'active'
  if (activePart && piece.nodeId === activePart.id) return 'context'
  return null
}

// A piece made only of punctuation (the comma and hyphen inside "2,6-dione")
// would be a tab stop whose name is "comma". Keep it hoverable, not tabbable.
const WORDLIKE = /[\p{L}\p{N}]/u

// The indexes of `pieces` (from sliceName) that are keyboard stops: every
// piece with a letter or digit, plus the first piece of any node that has
// none (the racemate mark "+-"), so no node becomes unreachable by keyboard.
export function tabStops(pieces) {
  const stops = new Set()
  const covered = new Set()
  pieces.forEach((piece, index) => {
    if (piece.nodeId && WORDLIKE.test(piece.text)) {
      stops.add(index)
      covered.add(piece.nodeId)
    }
  })
  pieces.forEach((piece, index) => {
    if (piece.nodeId && !covered.has(piece.nodeId)) {
      stops.add(index)
      covered.add(piece.nodeId)
    }
  })
  return stops
}
