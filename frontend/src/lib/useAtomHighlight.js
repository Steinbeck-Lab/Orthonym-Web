import { useCallback, useEffect, useRef, useState } from 'react'

import { atomRefsOf, sanitizeSvg } from './svgHighlight.js'
import { nodeById } from './nameTargets.js'

const SVG_NS = 'http://www.w3.org/2000/svg'
const GLOW_RADIUS = '13'
const GLOW_OPACITY = '0.85'

/**
 * Which atoms should light up for the node `activeId`? Pure, so it is
 * tested without a browser. Returns a Set, or null for "highlight nothing".
 */
export function highlightTargets(data, activeId) {
  const node = nodeById(data?.nodes, activeId)
  return node?.lights?.length ? new Set(node.lights) : null
}

/**
 * Should one SVG element be highlighted, given the target atom set?
 *
 * An element lights up only when EVERY atom it references is inside the set --
 * a bond between a highlighted atom and a non-highlighted one stays neutral,
 * so the highlighted region's edge reads as a clean boundary rather than a
 * half-lit connecting bond. Loosening `every` to `some` is a one-word change
 * with an obvious visual consequence and nothing to catch it.
 */
export function shouldHighlight(classAttr, targetSet) {
  if (targetSet === null) return false
  const refs = atomRefsOf(classAttr)
  return refs.length > 0 && refs.every((i) => targetSet.has(i))
}

/**
 * Render a decomposition's SVG and highlight the atoms of the active node.
 *
 * Extracted from Explain.jsx and Teach.jsx, which carried 113 byte-identical
 * lines of this each -- including all three of the browser workarounds below,
 * every one of which was found by looking at a real browser rather than by
 * reading. Two copies meant fixing any of them twice, with no frontend test
 * runner to catch the miss. CLAUDE.md already claimed these two files shared
 * everything; this is what makes that true.
 *
 * Returns the ref to attach to the (childless) wrapper div.
 *
 * @param {{svg?: string, nodes?: Array, atom_points?: Array}|null} data
 * @param {string|null} activeId  id of the hovered/pinned node
 */
export function useAtomHighlight(data, activeId) {
  // A CALLBACK ref kept in state, not a plain `useRef`, and the difference is
  // a bug that shipped: explaining the SAME input twice left an empty frame
  // where the structure had been.
  //
  // Why. Explain.jsx renders the whole result only while `phase === 'success'`,
  // so submitting again unmounts the wrapper div and mounts a fresh, EMPTY one.
  // The injection effect below is keyed on `data?.svg` -- the SVG string -- and
  // on a repeat submission the response is byte-identical, so the dependency
  // never changes, the effect never re-runs, and nothing refills the new node.
  // React skipped the one effect whose whole job was to put the picture back.
  //
  // A callback ref fires with the node on attach and null on detach, so
  // storing it in state makes the node itself a dependency: a remount
  // re-injects whether or not the SVG changed. Keying on the node rather than
  // on the payload also survives the next conditional wrapper someone adds,
  // which the string dependency could not.
  const [root, setRoot] = useState(null)
  const originalColorsRef = useRef(new Map())

  // Injects the sanitized SVG directly via the DOM, NOT via React's
  // dangerouslySetInnerHTML prop: this div renders with no JSX children at
  // all, so React never manages or diffs its contents once mounted --
  // every atom/bond element this effect creates and snapshots here stays
  // untouched by React across every later re-render (hover included). That
  // stability is what the highlight effect below depends on: it looks up
  // elements by object identity in `originalColorsRef`, which only holds
  // if React never silently replaces them out from under it.
  useEffect(() => {
    originalColorsRef.current = new Map()
    if (!root) return
    root.innerHTML = data?.svg ? sanitizeSvg(data.svg) : ''
    const elements = root.querySelectorAll('[class*="atom-"]')
    elements.forEach((el) => {
      originalColorsRef.current.set(el, { stroke: el.style.stroke, fill: el.style.fill })
    })
  }, [root, data?.svg])

  // Applies (or clears) the accent highlight for the active segment.
  useEffect(() => {
    if (!root) return
    const targetSet = highlightTargets(data, activeId)

    const svgEl = root.querySelector('svg')
    if (svgEl) {
      drawGlow(svgEl, targetSet, data?.atom_points || [])
    }

    originalColorsRef.current.forEach((original, el) => {
      if (shouldHighlight(el.getAttribute('class'), targetSet)) {
        el.style.stroke = 'var(--ink)'
        el.style.fill = 'var(--ink)'
      } else {
        el.style.stroke = original.stroke
        el.style.fill = original.fill
      }
    })
  }, [root, activeId, data])

  // Stable identity, so attaching it does not detach-and-reattach the node on
  // every render -- an inline arrow would, and each detach would blank the
  // SVG this hook has just injected.
  return useCallback((node) => setRoot(node), [])
}

/**
 * Paint a soft circle under each highlighted atom.
 *
 * The `.every()` walk in the caller can only ever light an element RDKit gave
 * a standalone atom-N node -- on caffeine that's just the six heteroatoms
 * (atom-1,3,5,7,10,13); every carbon appears solely inside bond paths like
 * "bond-10 atom-7 atom-11", so a carbon-only part (e.g. `methyl`) has no
 * dead-center element for that rule to ever select. This glow is additive: it
 * draws a circle straight from the atom's own pixel coordinates, independent
 * of what RDKit chose to label.
 */
function drawGlow(svgEl, targetSet, points) {
  let layer = svgEl.querySelector('#glow-layer')
  if (!layer) {
    layer = document.createElementNS(SVG_NS, 'g')
    layer.setAttribute('id', 'glow-layer')
    layer.setAttribute('filter', 'url(#glow-blur)')
    const defs = document.createElementNS(SVG_NS, 'defs')
    defs.innerHTML =
      '<filter id="glow-blur" x="-50%" y="-50%" width="200%" height="200%">' +
      '<feGaussianBlur stdDeviation="4" /></filter>'
    svgEl.insertBefore(defs, svgEl.firstChild)
    // RDKit always draws an opaque white background <rect> as the very
    // first element of the molecule drawing. Inserting the glow layer
    // as the literal first child (right after defs) would paint it
    // BEHIND that rect, where it is fully hidden -- confirmed live in a
    // real browser: the three glow circles existed in the DOM with
    // correct geometry/fill/opacity, yet rendered zero visible pixels.
    // Insert after that background rect instead: still behind every
    // bond and atom-label path (so those stay readable on top), but
    // above the opaque background, which is what "behind the
    // molecule" actually requires.
    // The defs.nextSibling branch is a last resort, not a real defense:
    // it only re-triggers this same invisible-glow bug (silently, no
    // error) if RDKit ever emits no <rect> at all, and it doesn't
    // protect against a <rect> that isn't RDKit's first paint op
    // either -- anything painted before it would still sit under the
    // glow. Accepted for now because RDKit's SVG writer always emits
    // this background rect as its literal first drawing element; if
    // that ever changes, this insertion point needs revisiting.
    const background = svgEl.querySelector('rect')
    svgEl.insertBefore(layer, background ? background.nextSibling : defs.nextSibling)
  }
  layer.textContent = ''
  for (const index of targetSet || []) {
    const point = points[index]
    if (!point) continue
    const circle = document.createElementNS(SVG_NS, 'circle')
    circle.setAttribute('cx', point[0])
    circle.setAttribute('cy', point[1])
    circle.setAttribute('r', GLOW_RADIUS)
    // A style PROPERTY, not a presentation attribute: var() inside a
    // presentation attribute is newer SVG2 behavior with weaker
    // cross-engine guarantees, and it's inconsistent with the
    // pre-existing highlight, which already sets el.style.stroke /
    // el.style.fill rather than the matching attributes.
    circle.style.fill = 'var(--glow, #ffd400)'
    circle.setAttribute('opacity', GLOW_OPACITY)
    layer.appendChild(circle)
  }
}
