import { useState } from 'react'
import { Link } from 'react-router-dom'
import { explainMolecule, explainName } from '../lib/api'
import { nameTargets, sliceName } from '../lib/nameTargets'
import { segmentAtPath } from '../lib/svgHighlight'
import { useAtomHighlight } from '../lib/useAtomHighlight'
import './Explain.css'

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

  const svgWrapperRef = useAtomHighlight(data, activePath)

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
  // All-or-nothing is a SEGMENT-level property only: a top-level part with no
  // name_range means spans could not be proven for this name at all, so the
  // whole hoverable name falls back to the plain part list. A CHILD with no
  // name_range is ordinary and expected (ethanol's suffix locant is never
  // written, caffeine's modifier locant lives inside "1H-", DDT's `chloro`
  // groups five atoms behind a span that has no room for its own `4`) -- it
  // simply renders as inert text, never as a reason to blank the page.
  const spansAvailable = segments.length > 0 && segments.every((segment) => segment.name_range)
  const activeSegment = segmentAtPath(segments, activePath)

  return (
    <>
      <div className="page-head page-shell">
        <h1 className="page-head__title">Show the working</h1>
        <p className="page-head__lede">
          Orthonym doesn&rsquo;t just produce a name &mdash; on this page it shows its work. Enter
          an IUPAC name or a SMILES string, then hover (or tap) any part of the decomposed name to
          see exactly which atoms it refers to.
        </p>
      </div>

      <main className="workspace" aria-label="Explain a name">
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

          <div className="field">
            <label htmlFor="explain-smiles-input" className="field__label">
              {mode === 'name' ? 'IUPAC name' : 'SMILES'}
            </label>
            <input
              id="explain-smiles-input"
              type="text"
              className="field__control"
              spellCheck={false}
              autoCorrect="off"
              autoCapitalize="off"
              placeholder={mode === 'name' ? 'e.g. ethanol' : 'e.g. CCO'}
              value={smilesInput}
              onChange={(event) => setSmilesInput(event.target.value)}
            />
            <div className="explain-panel__actions">
              <button type="submit" className="btn" disabled={isLoading}>
                {isLoading ? 'Explaining…' : 'Explain'}
              </button>
              {validationNote && (
                <p className="explain-panel__note" role="status">
                  {validationNote}
                </p>
              )}
            </div>
          </div>

          <div className="examples" role="group" aria-label="Try a curated example">
            <span className="examples__label">Try one:</span>
            <ul className="examples__list">
              {EXAMPLES.map((example) => (
                <li key={example.smiles}>
                  <button
                    type="button"
                    className="chip"
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

        <p className="page-about-note">
          Read how this works, and Orthonym&rsquo;s measured accuracy, on the{' '}
          <Link to="/about" className="about-link">
            About
          </Link>{' '}
          page.
        </p>
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
                  {name && spansAvailable ? (
                    <p className="explain-result__name explain-name" aria-live="polite">
                      {sliceName(name, nameTargets(segments)).map((piece, index) =>
                        piece.path === null ? (
                          <span key={index}>{piece.text}</span>
                        ) : (
                          <span
                            key={index}
                            className={`explain-name__part${
                              activePath === piece.path ? ' explain-name__part--active' : ''
                            }`}
                            onMouseEnter={() => setHoveredPath(piece.path)}
                            onMouseLeave={() => setHoveredPath(null)}
                            onFocus={() => setHoveredPath(piece.path)}
                            onBlur={() => setHoveredPath(null)}
                            onClick={() => togglePath(piece.path)}
                            // role="button" promises keyboard operation that a
                            // <span> does not implement on its own: without
                            // this, Enter and Space did nothing and a keyboard
                            // user could glow a part by focusing it but never
                            // PIN one, where the fallback list's real <button>
                            // elements can (WCAG 2.1.1). preventDefault stops
                            // Space from scrolling the page.
                            onKeyDown={(event) => {
                              if (event.key === 'Enter' || event.key === ' ') {
                                event.preventDefault()
                                togglePath(piece.path)
                              }
                            }}
                            tabIndex={0}
                            role="button"
                            // Mirrors the PINNED state, not activePath: focus
                            // alone sets hoveredPath, and announcing a merely
                            // focused part as "pressed" would be false.
                            aria-pressed={pinnedPath === piece.path}
                          >
                            {piece.text}
                          </span>
                        )
                      )}
                    </p>
                  ) : (
                    <p className="explain-result__name" aria-live="polite">
                      {name && renderAnnotatedName(name, segments, activePath)}
                    </p>
                  )}
                  {/* /api/explain returns the name and its decomposition, but
                      no confidence tier, so this page cannot show one. Saying
                      that plainly is the honest option; inventing a tier mark
                      here would misrepresent confidence, which the product
                      forbids. Translate is where the tier lives. */}
                  <p className="explain-tier-note">
                    This page shows how the name breaks down. It does not check the
                    name&rsquo;s confidence tier &mdash; run the same molecule through{' '}
                    <Link to="/" className="about-link">
                      Translate
                    </Link>{' '}
                    to see whether it is a verified PIN, a fallback, or a best effort.
                  </p>
                </div>

                {/* A partial result is a real case (see runExplain): the
                    backend can name and draw a molecule and still fail to
                    decompose that name, and it then carries `error` alongside
                    `name`/`svg`. `apiError` used to render only in the
                    phase === 'error' branch, so for TNT the user got a drawn,
                    named structure with an empty part list and NO reason at
                    all. Shown here as a notice rather than a blocking error,
                    so nothing that WAS drawn gets hidden. */}
                {apiError && (
                  <p className="explain-result__notice" role="status">
                    {apiError}
                  </p>
                )}

                <div className="explain-result__body">
                  <div
                    className="explain-result__diagram"
                    role="img"
                    aria-label={`2D structure diagram of ${name}`}
                    ref={svgWrapperRef}
                  />

                  {spansAvailable ? (
                    <div className="explain-detail">
                      {activeSegment ? (
                        <>
                          <h3 className="explain-detail__label">{activeSegment.label}</h3>
                          <p className="explain-detail__explanation">
                            {activeSegment.explanation}
                          </p>
                        </>
                      ) : (
                        <p className="explain-detail__hint">
                          Move your pointer across the name above to see what each part means.
                        </p>
                      )}
                    </div>
                  ) : (
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
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      </section>
      </main>
    </>
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
