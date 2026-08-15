import { useEffect, useRef, useState } from 'react'
import DOMPurify from 'dompurify'
import { explainMolecule } from '../lib/api'
import './Explain.css'

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

// Curated examples spanning the three real outcomes this page can show:
// a suffix STITCH's explainer confirms structurally, a name it can't yet
// decompose (retained/ring name), and a name with real substituent
// structure from OpenSTOUT's own tree data.
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

// phase: 'idle' | 'loading' | 'success' | 'error' (mirrors IupacToSmiles.jsx)
function Explain() {
  const [smilesInput, setSmilesInput] = useState('')
  const [phase, setPhase] = useState('idle')
  const [data, setData] = useState(null)
  const [apiError, setApiError] = useState(null)
  const [fetchError, setFetchError] = useState(null)
  const [validationNote, setValidationNote] = useState(null)
  const [hoveredIndex, setHoveredIndex] = useState(null)
  const [pinnedIndex, setPinnedIndex] = useState(null)

  const svgWrapperRef = useRef(null)
  const originalColorsRef = useRef(new Map())

  const activeIndex = pinnedIndex ?? hoveredIndex

  function runExplain(smiles) {
    setFetchError(null)
    setPhase('loading')
    setPinnedIndex(null)
    setHoveredIndex(null)

    explainMolecule(smiles)
      .then((result) => {
        if (result.error) {
          setApiError(result.error)
          setData(null)
          setPhase('error')
        } else {
          setData(result)
          setApiError(null)
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
      setValidationNote('Enter a SMILES string before explaining.')
      return
    }
    setValidationNote(null)
    runExplain(trimmed)
  }

  function handleExamplePick(example) {
    if (phase === 'loading') return
    setSmilesInput(example.smiles)
    setValidationNote(null)
    runExplain(example.smiles)
  }

  function toggleSegment(index) {
    setPinnedIndex((current) => (current === index ? null : index))
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
    const segment = activeIndex !== null ? data?.segments?.[activeIndex] : null
    const targetSet = segment ? new Set(segment.atom_indices) : null

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
  }, [activeIndex, data])

  const isLoading = phase === 'loading'
  const name = data?.name
  const segments = data?.segments || []
  // Whether a segment was actually SMARTS-confirmed against the real
  // structure, as opposed to the honest "undecomposed" fallback (a name,
  // but nothing STITCH could confidently point to). The outer patch's
  // border must track this same distinction the segment buttons already
  // do -- the one accent thread means "confirmed," never "a name exists."
  const hasConfirmedSuffix = segments.some((segment) => segment.kind === 'suffix')

  return (
    <section className="explain-page page-shell" aria-label="Explain a name">
      <h1 className="explain-page__title">Explain</h1>
      <p className="explain-page__lead">
        STITCH doesn&rsquo;t just produce a name &mdash; on this page it shows its work. Enter a
        SMILES string and hover (or tap) a highlighted part of the name to see exactly which
        atoms earned it.
      </p>

      <section className="explain-panel" aria-label="Explain a molecule">
        <form onSubmit={handleSubmit} noValidate>
          <div className="explain-panel__grid">
            <div className="explain-panel__field">
              <label htmlFor="explain-smiles-input" className="explain-panel__label">
                SMILES
              </label>
              <input
                id="explain-smiles-input"
                type="text"
                className="explain-panel__input"
                spellCheck={false}
                autoCorrect="off"
                autoCapitalize="off"
                placeholder="e.g. CCO"
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
                Highlights come from real structure matching, never a guess.
              </p>
              <p className="explain-aside__body">
                A suffix (like &ldquo;-ol&rdquo; or &ldquo;-oic acid&rdquo;) is only highlighted
                once STITCH confirms the matching group is really there in the structure. When a
                name doesn&rsquo;t decompose into a part STITCH recognizes this confidently, it
                says so instead of guessing which piece means what.
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
            Could not reach STITCH&rsquo;s backend ({fetchError}). Is it running on{' '}
            <code>localhost:8000</code>?
          </p>
        )}

        <div aria-live="polite">
          {phase === 'idle' && (
            <div className="explain-patch explain-patch--idle">
              <p className="explain-patch__empty-note">
                Nothing to explain yet &mdash; enter a SMILES string above, or try one of the
                examples.
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
                hasConfirmedSuffix ? ' explain-patch--success' : ' explain-patch--undecomposed'
              }`}
            >
              <div className="explain-result">
                <div className="explain-result__name-row">
                  <span className="explain-result__name-label">Name</span>
                  <p className="explain-result__name" aria-live="polite">
                    {name && renderAnnotatedName(name, segments, activeIndex)}
                  </p>
                </div>

                <div className="explain-result__body">
                  <div
                    className="explain-result__diagram"
                    role="img"
                    aria-label={`2D structure diagram of ${name}`}
                    ref={svgWrapperRef}
                  />

                  <div className="explain-segments" role="group" aria-label="Named parts">
                    {segments.map((segment, index) => (
                      <button
                        key={`${segment.kind}-${index}`}
                        type="button"
                        className={`explain-segment explain-segment--${segment.kind}${
                          activeIndex === index ? ' explain-segment--active' : ''
                        }`}
                        aria-pressed={pinnedIndex === index}
                        onMouseEnter={() => setHoveredIndex(index)}
                        onMouseLeave={() => setHoveredIndex(null)}
                        onFocus={() => setHoveredIndex(index)}
                        onBlur={() => setHoveredIndex(null)}
                        onClick={() => toggleSegment(index)}
                      >
                        <span className="explain-segment__label">{segment.label}</span>
                        <span className="explain-segment__explanation">
                          {segment.explanation}
                        </span>
                      </button>
                    ))}
                  </div>
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
function renderAnnotatedName(name, segments, activeIndex) {
  const segment = activeIndex !== null ? segments[activeIndex] : null
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
