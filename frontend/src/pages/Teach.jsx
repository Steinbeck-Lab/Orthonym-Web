import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import DOMPurify from 'dompurify'
import { explainMolecule } from '../lib/api'
import { nameTargets, sliceName } from '../lib/nameTargets'
import './Teach.css'

// The SVG comes from STITCH's own backend (RDKit-generated structure
// drawing, never raw user text echoed into markup), but it's injected
// directly into the DOM (see the effect below) -- unlike an <img
// src="data:..."> elsewhere in this app, inlined SVG becomes live DOM and
// could execute embedded scripts/handlers if the backend or a future
// change ever introduced one. Sanitize defensively regardless of the
// current trusted source. `class`/`style` are explicitly kept: the
// hover-highlighting mechanism below depends on both (atom-N/bond-N
// classes to find elements, inline style to read/restore their original
// stroke and fill colors).
function sanitizeSvg(svg) {
  return DOMPurify.sanitize(svg, {
    USE_PROFILES: { svg: true, svgFilters: true },
    ADD_ATTR: ['class', 'style'],
  })
}

// Matches a CSS class attribute like "bond-1 atom-1 atom-2" or "atom-2" --
// pulls out every atom-N reference on that SVG element.
const ATOM_REF_RE = /atom-(\d+)/g

function atomRefsOf(classAttr) {
  if (!classAttr) return []
  return [...classAttr.matchAll(ATOM_REF_RE)].map((m) => Number(m[1]))
}

// The vendored standalone Ketcher app posts window.parent a single
// {eventType: "init"} message once its structure service has actually
// finished initialising. That fires LATER than the iframe's own `load`
// event, which only means the HTML shell downloaded. Listening for this
// message is the real "editor is interactive" signal; a bare onLoad
// handler races the startup and can grab `contentWindow.ketcher` before it
// exists. Same pattern as StructureToIupac.jsx, deliberately duplicated
// rather than abstracted -- the two pages will diverge.
const READY_TIMEOUT_MS = 20000

// Resolves a dotted path like "0.2" to its segment: top-level index 0, then
// its child index 2. Returns null for a stale path, which happens normally
// when a new molecule replaces the old one while something is pinned.
function segmentAtPath(segments, path) {
  if (path === null || path === undefined) return null
  const parts = String(path).split('.').map(Number)
  let node = segments?.[parts[0]]
  for (let i = 1; i < parts.length && node; i += 1) {
    node = node.children?.[parts[i]]
  }
  return node || null
}

function Teach() {
  const iframeRef = useRef(null)
  const [editorState, setEditorState] = useState('loading') // loading | ready | error
  const [phase, setPhase] = useState('idle') // idle | working | done | failed
  const [data, setData] = useState(null)
  const [note, setNote] = useState(null)
  const [hoveredPath, setHoveredPath] = useState(null)
  const [pinnedPath, setPinnedPath] = useState(null)
  const activePath = pinnedPath ?? hoveredPath
  const svgWrapperRef = useRef(null)
  const originalColorsRef = useRef(new Map())

  useEffect(() => {
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
  }, [])

  function handleFrameLoad() {
    // Fast networks and warm caches can beat our listener into place.
    if (iframeRef.current?.contentWindow?.ketcher) {
      setEditorState('ready')
    }
  }

  function handleFrameError() {
    setEditorState('error')
  }

  async function handleName() {
    if (phase === 'working') return
    setNote(null)
    setPinnedPath(null)
    setHoveredPath(null)
    const ketcher = iframeRef.current?.contentWindow?.ketcher
    if (!ketcher) {
      setNote('The drawing area is still starting up. Give it a moment and try again.')
      return
    }
    let structure = ''
    try {
      structure = (await ketcher.getSmiles()) || ''
    } catch {
      setNote('Could not read your drawing. Try drawing it again.')
      return
    }
    structure = structure.trim()
    if (!structure) {
      setNote('Draw a molecule first, then press Name it.')
      return
    }
    setPhase('working')
    try {
      const result = await explainMolecule(structure)
      setData(result)
      setPhase(result.name ? 'done' : 'failed')
    } catch {
      setNote('Could not reach the naming service. Check it is running and try again.')
      setPhase('idle')
    }
  }

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
    const root = svgWrapperRef.current
    if (!root) return
    root.innerHTML = data?.svg ? sanitizeSvg(data.svg) : ''
    const elements = root.querySelectorAll('[class*="atom-"]')
    elements.forEach((el) => {
      originalColorsRef.current.set(el, { stroke: el.style.stroke, fill: el.style.fill })
    })
  }, [data?.svg])

  // Applies (or clears) the accent highlight for the active segment. An
  // element only lights up when EVERY atom it references is inside the
  // segment's atom set -- a bond between a highlighted atom and a
  // non-highlighted one stays neutral, so the highlighted region's edge
  // reads as a clean boundary rather than a half-lit connecting bond.
  useEffect(() => {
    const root = svgWrapperRef.current
    if (!root) return
    const segment = segmentAtPath(data?.segments, activePath)
    // Referential segments (a hydro prefix) own no atoms, so atom_indices is
    // empty and highlight_atoms is the only thing to light up. Owning
    // segments usually have both; fall back so neither case goes dark.
    const highlight =
      segment && segment.highlight_atoms?.length
        ? segment.highlight_atoms
        : segment?.atom_indices
    const targetSet = highlight?.length ? new Set(highlight) : null

    // The `.every()` walk below can only ever light an element RDKit gave a
    // standalone atom-N node -- on caffeine that's just the six heteroatoms
    // (atom-1,3,5,7,10,13); every carbon appears solely inside bond paths
    // like "bond-10 atom-7 atom-11", so a carbon-only part (e.g. `methyl`)
    // has no dead-center element for that rule to ever select. This glow is
    // additive: it draws a circle straight from the atom's own pixel
    // coordinates, independent of what RDKit chose to label.
    const svgEl = root.querySelector('svg')
    if (svgEl) {
      let layer = svgEl.querySelector('#glow-layer')
      if (!layer) {
        layer = document.createElementNS('http://www.w3.org/2000/svg', 'g')
        layer.setAttribute('id', 'glow-layer')
        layer.setAttribute('filter', 'url(#glow-blur)')
        const defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs')
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
      const points = data?.atom_points || []
      for (const index of targetSet || []) {
        const point = points[index]
        if (!point) continue
        const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle')
        circle.setAttribute('cx', point[0])
        circle.setAttribute('cy', point[1])
        circle.setAttribute('r', '13')
        // A style PROPERTY, not a presentation attribute: var() inside a
        // presentation attribute is newer SVG2 behavior with weaker
        // cross-engine guarantees, and it's inconsistent with the
        // pre-existing highlight below, which already sets el.style.stroke
        // / el.style.fill rather than the matching attributes.
        circle.style.fill = 'var(--glow, #ffd400)'
        circle.setAttribute('opacity', '0.85')
        layer.appendChild(circle)
      }
    }

    originalColorsRef.current.forEach((original, el) => {
      const refs = atomRefsOf(el.getAttribute('class'))
      const shouldHighlight =
        targetSet !== null && refs.length > 0 && refs.every((i) => targetSet.has(i))
      if (shouldHighlight) {
        el.style.stroke = 'var(--ink)'
        el.style.fill = 'var(--ink)'
      } else {
        el.style.stroke = original.stroke
        el.style.fill = original.fill
      }
    })
  }, [activePath, data])

  return (
    <>
      <div className="page-head page-shell">
        <h1 className="page-head__title">Draw it, learn its name</h1>
        <p className="page-head__lede">
          Draw a structure and press Name it. You get the name, and you can point at any part of
          the name to see which atoms it describes.
        </p>
      </div>

      <main className="workspace workspace--draw" aria-label="Learn a name">
        <section className="teach__draw">
          {editorState === 'error' ? (
            <p className="teach__editor-error" role="alert">
              The drawing area did not load. Reload the page to try again.
            </p>
          ) : (
            <iframe
              ref={iframeRef}
              title="Molecule drawing area"
              className="teach__editor"
              src="/standalone/index.html"
              onLoad={handleFrameLoad}
              onError={handleFrameError}
            />
          )}
          <button
            type="button"
            className="btn"
            onClick={handleName}
            disabled={editorState !== 'ready' || phase === 'working'}
          >
            {phase === 'working' ? 'Working…' : 'Name it'}
          </button>
          {note && (
            <p className="teach__note" role="status">
              {note}
            </p>
          )}
        </section>

        <section className="teach__output" aria-label="Result">
          {phase === 'done' && data && (
            <div className="teach__result">
              <p className="teach__name" aria-live="polite">
                {(() => {
                  const segments = data.segments || []
                  const spansAvailable =
                    segments.length > 0 && segments.every((s) => s.name_range)
                  if (!spansAvailable) return data.name
                  return sliceName(data.name, nameTargets(segments)).map((piece, index) =>
                    piece.path === null ? (
                      <span key={index}>{piece.text}</span>
                    ) : (
                      <span
                        key={index}
                        className={`teach__part${
                          activePath === piece.path ? ' teach__part--active' : ''
                        }`}
                        onMouseEnter={() => setHoveredPath(piece.path)}
                        onMouseLeave={() => setHoveredPath(null)}
                        onFocus={() => setHoveredPath(piece.path)}
                        onBlur={() => setHoveredPath(null)}
                        onClick={() =>
                          setPinnedPath((c) => (c === piece.path ? null : piece.path))
                        }
                        onKeyDown={(event) => {
                          if (event.key === 'Enter' || event.key === ' ') {
                            event.preventDefault()
                            setPinnedPath((c) => (c === piece.path ? null : piece.path))
                          }
                        }}
                        tabIndex={0}
                        role="button"
                        aria-pressed={pinnedPath === piece.path}
                      >
                        {piece.text}
                      </span>
                    )
                  )
                })()}
              </p>

              {/* /api/explain carries no confidence tier, so this route
                  cannot show one. Say so rather than invent a mark. */}
              <p className="teach__tier-note">
                This shows how the name breaks down. It does not check the name&rsquo;s
                confidence tier &mdash; run the same molecule through{' '}
                <Link to="/" className="about-link">
                  Translate
                </Link>{' '}
                to see whether it is a verified PIN, a fallback, or a best effort.
              </p>

              <div className="teach__body">
                <div className="teach__structure" ref={svgWrapperRef} />
                <div className="teach__detail">
                  {segmentAtPath(data.segments || [], activePath) ? (
                    <>
                      <h2 className="teach__detail-label">
                        {segmentAtPath(data.segments, activePath).label}
                      </h2>
                      <p>{segmentAtPath(data.segments, activePath).explanation}</p>
                    </>
                  ) : (
                    <p className="teach__hint">
                      Point at any part of the name above to see what it means.
                    </p>
                  )}
                </div>
              </div>

              <ol className="teach__parts">
                {(data.segments || []).map((segment, index) => (
                  <li key={index}>
                    <strong>{segment.label}</strong>
                    <span>{segment.explanation}</span>
                  </li>
                ))}
              </ol>
            </div>
          )}

          {phase === 'failed' && (
            <p className="teach__note" role="status">
              We could not work out a name for that molecule with confidence, so we are
              not going to guess. Try a simpler structure.
            </p>
          )}

          {(phase === 'idle' || phase === 'working') && !note && (
            <p className="teach__empty-note">
              Draw a molecule and press Name it to see its name here.
            </p>
          )}
        </section>
      </main>
    </>
  )
}

export default Teach
