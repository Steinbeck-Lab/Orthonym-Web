import { useEffect, useRef, useState } from 'react'
import DOMPurify from 'dompurify'
import { explainMolecule, explainName } from '../lib/api'
import './Explain.css'

// The SVG comes from Orthonym's own backend (RDKit-generated structure
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

// Curated structures spanning what the decomposition really does now that
// it comes from OPSIN's own parse tree rather than SMARTS rules: a simple
// parent + suffix (ethanol), a molecule whose internal symmetry makes some
// parts genuinely unmappable so they report as `unmapped` while their
// siblings survive (ibuprofen), and a bare ring parent with no principal
// characteristic group at all (benzene) -- which decomposes perfectly and
// simply has no suffix.
const EXAMPLES = [
  { label: 'ethanol', smiles: 'CCO' },
  { label: 'ibuprofen', smiles: 'CC(C)Cc1ccc(cc1)C(C)C(=O)O' },
  { label: 'benzene', smiles: 'c1ccccc1' },
]

// Matches a CSS class attribute like "bond-1 atom-1 atom-2" or "atom-2" --
// pulls out every atom-N reference on that SVG element.
const ATOM_REF_RE = /atom-(\d+)/g

function atomRefsOf(classAttr) {
  if (!classAttr) return []
  return [...classAttr.matchAll(ATOM_REF_RE)].map((m) => Number(m[1]))
}

// Resolves a dotted path like "0.2" to its segment: top-level index 0, then
// its child index 2. Returns null for a stale path, which happens normally
// when `data` changes while something is still pinned.
function segmentAtPath(segments, path) {
  if (path === null || path === undefined) return null
  const parts = String(path).split('.').map(Number)
  let node = segments?.[parts[0]]
  for (let i = 1; i < parts.length && node; i += 1) {
    node = node.children?.[parts[i]]
  }
  return node || null
}

function SegmentNode({ segment, path, activePath, setHoveredPath, togglePath }) {
  const isActive = activePath === path
  return (
    <li className="explain-segment__item">
      <button
        type="button"
        className={`explain-segment explain-segment--${segment.kind}${
          isActive ? ' explain-segment--active' : ''
        }`}
        onMouseEnter={() => setHoveredPath(path)}
        onMouseLeave={() => setHoveredPath(null)}
        onFocus={() => setHoveredPath(path)}
        onBlur={() => setHoveredPath(null)}
        onClick={() => togglePath(path)}
        aria-pressed={isActive}
      >
        <span className="explain-segment__label">{segment.label}</span>
        <span className="explain-segment__explanation">{segment.explanation}</span>
      </button>
      {segment.children?.length > 0 && (
        <ul className="explain-segment__children">
          {segment.children.map((child, index) => (
            <SegmentNode
              key={`${path}.${index}`}
              segment={child}
              path={`${path}.${index}`}
              activePath={activePath}
              setHoveredPath={setHoveredPath}
              togglePath={togglePath}
            />
          ))}
        </ul>
      )}
    </li>
  )
}

// phase: 'idle' | 'loading' | 'success' | 'error' (mirrors IupacToSmiles.jsx)
function Explain() {
  const [smilesInput, setSmilesInput] = useState('')
  const [mode, setMode] = useState('name') // 'name' | 'smiles'
  const [phase, setPhase] = useState('idle')
  const [data, setData] = useState(null)
  const [apiError, setApiError] = useState(null)
  const [fetchError, setFetchError] = useState(null)
  const [validationNote, setValidationNote] = useState(null)
  const [hoveredPath, setHoveredPath] = useState(null)
  const [pinnedPath, setPinnedPath] = useState(null)

  const svgWrapperRef = useRef(null)
  const originalColorsRef = useRef(new Map())

  const activePath = pinnedPath ?? hoveredPath

  function togglePath(path) {
    setPinnedPath((current) => (current === path ? null : path))
  }

  // requestMode defaults to the current mode state, but callers that need
  // to force a specific endpoint in the SAME tick (see handleExamplePick)
  // must pass it explicitly -- setMode() would not be visible to this
  // function's `mode` closure until the next render.
  function runExplain(value, requestMode = mode) {
    setFetchError(null)
    setPhase('loading')
    setPinnedPath(null)
    setHoveredPath(null)

    const request = requestMode === 'name' ? explainName(value) : explainMolecule(value)

    request
      .then((result) => {
        // A PARTIAL result is a real case, not a contradiction: the
        // structure-in path can name a molecule and render it, yet fail to
        // decompose the name. Verified live -- Orthonym names TNT's SMILES
        // "2,4,6-trinitrotoluene", which OPSIN itself rejects ("Multiple
        // locants without a multiplier"). That response carries `name` and
        // `svg` alongside `error`. Throwing it away would hide a structure
        // we successfully drew, so keep the data and show the error beside
        // it. Only a result with nothing to show is a bare error.
        const hasSomethingToShow = Boolean(result.svg || result.name)
        setApiError(result.error || null)
        if (result.error && !hasSomethingToShow) {
          setData(null)
          setPhase('error')
        } else {
          setData(result)
          setPhase('success')
        }
      })
      .catch((err) => {
        setFetchError(err?.message || 'unknown network error')
        setPhase('idle')
      })
  }

  function handleSubmit(event) {
    event.preventDefault()
    if (phase === 'loading') return
    const trimmed = smilesInput.trim()
    if (!trimmed) {
      setValidationNote(
        mode === 'name'
          ? 'Enter an IUPAC name before explaining.'
          : 'Enter a SMILES string before explaining.'
      )
      return
    }
    setValidationNote(null)
    runExplain(trimmed)
  }

  function handleExamplePick(example) {
    if (phase === 'loading') return
    // EXAMPLES are curated SMILES (not names). Force smiles mode -- both
    // the toggle UI and the actual request -- so picking one while in the
    // default 'name' mode doesn't send a SMILES string to explainName().
    setMode('smiles')
    setSmilesInput(example.smiles)
    setValidationNote(null)
    runExplain(example.smiles, 'smiles')
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
        el.style.stroke = 'var(--accent)'
        el.style.fill = 'var(--accent)'
      } else {
        el.style.stroke = original.stroke
        el.style.fill = original.fill
      }
    })
  }, [activePath, data])

  const isLoading = phase === 'loading'
  const name = data?.name
  const segments = data?.segments || []
  // Whether any part of this name was actually pinned to real atoms. The
  // outer patch's accent border means "confirmed," never "a name exists,"
  // so it is earned by at least one MAPPED part -- a part that is not
  // `unmapped` owns or highlights atoms traced to OPSIN's own output.
  //
  // This used to test `kind === 'suffix'`, which silently changed meaning
  // when the SMARTS design was retired. Back then "no suffix segment" was
  // the only way a name could fail to decompose. It now means only "this
  // molecule has no principal characteristic group," which is an ordinary,
  // fully-decomposed outcome: benzene, TNT and DDT all decompose completely
  // and have no suffix, yet every one of them rendered with the plain
  // non-confirmed border.
  const hasMappedParts = segments.some((segment) => segment.kind !== 'unmapped')

  return (
    <section className="explain-page page-shell" aria-label="Explain a name">
      <h1 className="explain-page__title">Explain</h1>
      <p className="explain-page__lead">
        Orthonym doesn&rsquo;t just produce a name &mdash; on this page it shows its work. Enter an
        IUPAC name or a SMILES string, then hover (or tap) any part of the decomposed name to see
        exactly which atoms it refers to.
      </p>

      <section className="explain-panel" aria-label="Explain a molecule">
        <form onSubmit={handleSubmit} noValidate>
          <fieldset className="explain-mode">
            <legend className="explain-mode__legend">Input</legend>
            {[
              { value: 'name', label: 'IUPAC name' },
              { value: 'smiles', label: 'SMILES' },
            ].map((option) => (
              <label key={option.value} className="explain-mode__option">
                <input
                  type="radio"
                  name="explain-mode"
                  value={option.value}
                  checked={mode === option.value}
                  onChange={() => { setMode(option.value); setValidationNote(null) }}
                  disabled={phase === 'loading'}
                />
                {option.label}
              </label>
            ))}
          </fieldset>

          <div className="explain-panel__grid">
            <div className="explain-panel__field">
              <label htmlFor="explain-smiles-input" className="explain-panel__label">
                {mode === 'name' ? 'IUPAC name' : 'SMILES'}
              </label>
              <input
                id="explain-smiles-input"
                type="text"
                className="explain-panel__input"
                spellCheck={false}
                autoCorrect="off"
                autoCapitalize="off"
                placeholder={mode === 'name' ? 'e.g. ethanol' : 'e.g. CCO'}
                value={smilesInput}
                onChange={(event) => setSmilesInput(event.target.value)}
              />
              <div className="explain-panel__actions">
                <button type="submit" className="explain-button" disabled={isLoading}>
                  {isLoading ? 'Explaining…' : 'Explain'}
                </button>
                {validationNote && (
                  <p className="explain-panel__note" role="status">
                    {validationNote}
                  </p>
                )}
              </div>
            </div>

            <aside className="explain-aside" aria-label="How this works">
              <p className="explain-aside__lead">
                Every highlight comes from OPSIN&rsquo;s own parse of the name, never a guess.
              </p>
              <p className="explain-aside__body">
                The name is broken into the parts OPSIN itself found &mdash; the parent skeleton,
                each substituent, the ending that names the main group, and prefixes that only
                move hydrogens around &mdash; and each part carries the atoms OPSIN built it from.
                Failure is per part: anything Orthonym can&rsquo;t pin to specific atoms is marked
                &ldquo;could not work out which atoms,&rdquo; and the parts around it are
                unaffected.
              </p>
            </aside>
          </div>

          <div className="explain-examples" role="group" aria-label="Try a curated example">
            <span className="explain-examples__label">Try one:</span>
            <ul className="explain-examples__list">
              {EXAMPLES.map((example) => (
                <li key={example.smiles}>
                  <button
                    type="button"
                    className="explain-chip"
                    disabled={isLoading}
                    onClick={() => handleExamplePick(example)}
                  >
                    {example.label}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </form>
      </section>

      <section className="explain-results" aria-label="Explanation">
        {fetchError && (
          <p className="explain-fetch-error" role="alert">
            Could not reach Orthonym&rsquo;s backend ({fetchError}). Is it running on{' '}
            <code>localhost:8000</code>?
          </p>
        )}

        <div aria-live="polite">
          {phase === 'idle' && (
            <div className="explain-patch explain-patch--idle">
              <p className="explain-patch__empty-note">
                Nothing to explain yet &mdash; enter an IUPAC name or a SMILES string above, or
                try one of the examples.
              </p>
            </div>
          )}

          {phase === 'loading' && (
            <div className="explain-patch explain-patch--loading" aria-busy="true">
              <span className="explain-patch__state-label">Naming and decomposing&hellip;</span>
              <div className="explain-patch__pending-cloth" aria-hidden="true">
                <span className="explain-patch__pending-dash" />
                <span className="explain-patch__pending-dash" />
                <span className="explain-patch__pending-dash" />
              </div>
            </div>
          )}

          {phase === 'error' && (
            <div className="explain-patch explain-patch--error" role="alert">
              <span className="explain-patch__state-label">
                {apiError || 'Could not explain this molecule'}
              </span>
              <div className="explain-patch__snip-wrap" aria-hidden="true">
                <span className="explain-patch__snip explain-patch__snip--a" />
                <span className="explain-patch__snip explain-patch__snip--b" />
              </div>
            </div>
          )}

          {phase === 'success' && (
            <div
              className={`explain-patch${
                hasMappedParts ? ' explain-patch--success' : ' explain-patch--unmapped'
              }`}
            >
              <div className="explain-result">
                <div className="explain-result__name-row">
                  <span className="explain-result__name-label">Name</span>
                  <p className="explain-result__name" aria-live="polite">
                    {name && renderAnnotatedName(name, segments, activePath)}
                  </p>
                </div>

                <div className="explain-result__body">
                  <div
                    className="explain-result__diagram"
                    role="img"
                    aria-label={`2D structure diagram of ${name}`}
                    ref={svgWrapperRef}
                  />

                  <ul className="explain-segments" aria-label="Named parts">
                    {segments.map((segment, index) => (
                      <SegmentNode
                        key={`${segment.kind}-${index}`}
                        segment={segment}
                        path={String(index)}
                        activePath={activePath}
                        setHoveredPath={setHoveredPath}
                        togglePath={togglePath}
                      />
                    ))}
                  </ul>
                </div>
              </div>
            </div>
          )}
        </div>
      </section>
    </section>
  )
}

// Renders `name` as plain text, except the active segment's own name_range
// (when it has one) is wrapped in a bracket-highlighted span -- e.g.
// hovering "carboxylic acid" on "2-[4-...]propanoic acid" shows
// prop[anoic acid] with the bracketed part in the accent color.
//
// NOTE: not covered by the task-9 brief, which only updated the segment
// buttons/highlight effect to use path-based lookup. This helper still took
// the old numeric activeIndex and did segments[activeIndex] -- a bare array
// index. That silently breaks for any nested child path (e.g. "0.2"), so it
// is updated here to the same segmentAtPath lookup used everywhere else,
// for consistency with the activeIndex -> activePath change made throughout
// the rest of this file.
function renderAnnotatedName(name, segments, activePath) {
  const segment = segmentAtPath(segments, activePath)
  const range = segment?.name_range
  if (!range) {
    return name
  }
  const [start, end] = range
  return (
    <>
      {name.slice(0, start)}
      <span className="explain-result__name-highlight">[{name.slice(start, end)}]</span>
      {name.slice(end)}
    </>
  )
}

export default Explain
