import { Fragment, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import ConfidenceReport from '../components/ConfidenceReport'
import { verdictKindFor } from '../lib/explainVerdict'
import { explainMolecule, explainName, translateBatch } from '../lib/api'
import { nameTargets, sliceName } from '../lib/nameTargets'
import { nameRuns, applyRuns } from '../lib/nameTypography'
import { Pieces } from '../components/Typeset'
import { segmentAtPath } from '../lib/svgHighlight'
import { useAtomHighlight } from '../lib/useAtomHighlight'
import { useKetcher } from '../lib/useKetcher'
import './Explain.css'
import Icon from '../components/Icon'
import ReportLink from '../components/ReportLink'

// Curated structures spanning what the decomposition really does now that
// it comes from OPSIN's own parse tree rather than SMARTS rules: a simple
// parent + suffix (ethanol), a molecule whose internal symmetry makes some
// parts genuinely unmappable so they report as `unmapped` while their
// siblings survive (ibuprofen), and a bare ring parent with no principal
// characteristic group at all (benzene) -- which decomposes perfectly and
// simply has no suffix.
//
// Each carries BOTH spellings because the chips follow the input tab: the
// IUPAC name tab fills the name and asks /api/explain to parse it, the SMILES
// tab fills the SMILES. The label stays the trivial name on either tab -- it
// is readable, and ibuprofen's SMILES in a chip would be 27 characters of
// punctuation.
const EXAMPLES = [
  { label: 'ethanol', name: 'ethanol', smiles: 'CCO' },
  {
    label: 'ibuprofen',
    name: '2-[4-(2-methylpropyl)phenyl]propanoic acid',
    smiles: 'CC(C)Cc1ccc(cc1)C(C)C(=O)O',
  },
  { label: 'benzene', name: 'benzene', smiles: 'c1ccccc1' },
]

// The switches the tier row is fetched with -- Home's defaults, since this
// page has no switches of its own. Named once so the request and the report
// link cannot state different settings.
const TIER_SETTINGS = { bestEffort: true, verify: true }

function SegmentNode({ segment, path, activePath, setHoveredPath, togglePath }) {
  const isActive = activePath === path
  return (
    <li className="explain-segment__item">
      <button
        type="button"
        className={`explain-segment explain-segment--${segment.kind}${
          segment.owns_atoms === false ? ' explain-segment--ref' : ''
        }${isActive ? ' explain-segment--active' : ''}`}
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
        <ul className="explain-segment__children" role="list">
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
  // 'name' | 'smiles' | 'draw'. Seeded from ?input= so the /structure and
  // /teach redirects land on the Draw tab -- an old bookmark keeps its
  // behaviour, not just its URL. Read once, at mount: this is an initial
  // value, not a controlled binding, so changing tabs must not fight the URL.
  const [mode, setMode] = useState(
    () => (new URLSearchParams(window.location.search).get('input') === 'draw' ? 'draw' : 'name')
  )
  const [phase, setPhase] = useState('idle')
  const [data, setData] = useState(null)
  const [apiError, setApiError] = useState(null)
  const [fetchError, setFetchError] = useState(null)
  const [validationNote, setValidationNote] = useState(null)
  const [hoveredPath, setHoveredPath] = useState(null)
  const [pinnedPath, setPinnedPath] = useState(null)
  // The confidence tier for a molecule Orthonym itself named. /api/explain does
  // not return one, so it comes from /api/translate alongside -- see
  // runExplain. Null in 'name' mode on purpose: the user supplied the name,
  // so there is no Orthonym verdict on it to report.
  const [tierRow, setTierRow] = useState(null)
  // The mode the DISPLAYED result was fetched with, which is not the same thing
  // as the tab currently selected. The tier disclosure below used to branch on
  // `mode` itself, so switching tabs after a result had landed rewrote the
  // verdict without re-running anything: explain a SMILES, then click the
  // IUPAC name tab, and a real "verified PIN" was replaced by "there is no
  // Orthonym confidence tier for it" -- a false statement about a name Orthonym
  // produced, and a tier hidden that PRODUCT.md principle 3 requires wherever
  // a name appears. The reverse lost the honest disclosure instead. Set by
  // runExplain alongside the request it describes.
  const [resultMode, setResultMode] = useState(null)
  // Which runExplain is current. The tier fetch below settles on its own
  // clock, after the explain request has already released the form, so a
  // reply from an EARLIER molecule could land after the next submit and pin
  // its tier -- and its "Report SMILES on GitHub" link -- under the new result.
  const latestRun = useRef(0)
  // enabled only on the Draw tab: the iframe does not exist otherwise, and an
  // armed readiness clock would time out against nothing and report the editor
  // broken before the user ever opened it.
  const { iframeRef, editorState, handleFrameLoad, handleFrameError, getKetcher } =
    useKetcher({ enabled: mode === 'draw' })
  const activePath = pinnedPath ?? hoveredPath

  // Reads the drawing and hands the SMILES to the SAME runExplain the typed
  // paths use, so a drawn molecule and a pasted one cannot diverge -- that
  // divergence is what /teach was: a second page around the same endpoint.
  async function handleDraw() {
    if (phase === 'loading') return
    setValidationNote(null)
    const ketcher = getKetcher()
    if (!ketcher) {
      setValidationNote('The drawing area is still starting up. Give it a moment and try again.')
      return
    }
    let structure = ''
    try {
      structure = (await ketcher.getSmiles()) || ''
    } catch {
      setValidationNote('Could not read your drawing. Try drawing it again.')
      return
    }
    structure = structure.trim()
    if (!structure) {
      setValidationNote('Draw a molecule first, then press Explain.')
      return
    }
    // 'smiles', not 'draw': a drawing IS a structure once Ketcher has given
    // us its SMILES, and runExplain only distinguishes name-vs-structure.
    setSmilesInput(structure)
    runExplain(structure, 'smiles')
  }

  function togglePath(path) {
    setPinnedPath((current) => (current === path ? null : path))
  }

  // requestMode defaults to the current tab, but a caller whose tab does not
  // NAME an endpoint must pass one explicitly. `handleDraw` is that caller and
  // now the only one: a drawing is a structure once Ketcher hands back its
  // SMILES, so it asks for 'smiles' while `mode` still reads 'draw'.
  // (It also matters for any caller that sets the tab in the same tick --
  // setMode() is not visible to this function's `mode` closure until the next
  // render. handleExamplePick used to be that caller and no longer is.)
  function runExplain(value, requestMode = mode) {
    setFetchError(null)
    setPhase('loading')
    setPinnedPath(null)
    setHoveredPath(null)

    const request = requestMode === 'name' ? explainName(value) : explainMolecule(value)

    // A drawn or typed STRUCTURE is something Orthonym names itself, so its
    // confidence tier is a real verdict and PRODUCT.md principle 3 requires it
    // wherever that name appears. /api/explain carries no tier -- Teach.jsx
    // used to note exactly that and simply show nothing -- so fetch it
    // alongside rather than dropping it.
    //
    // Fired in parallel, not chained: the breakdown is the point of this page
    // and must not wait on a second request. A tier that fails to arrive
    // leaves tierRow null and the breakdown still renders; a breakdown is
    // never blocked by the tier.
    setTierRow(null)
    setResultMode(requestMode)
    const run = ++latestRun.current
    if (requestMode !== 'name') {
      translateBatch([value], TIER_SETTINGS)
        .then((rows) => run === latestRun.current && setTierRow(rows?.[0] ?? null))
        .catch(() => run === latestRun.current && setTierRow(null))
    }

    request
      .then((result) => {
        // A PARTIAL result is a real case, not a contradiction: the
        // structure-in path can name a molecule and render it, yet fail to
        // decompose the name. Verified live -- the Orthonym engine names TNT's
        // SMILES "2,4,6-trinitrotoluene", which OPSIN itself rejects ("Multiple
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

  // The chips FOLLOW the current tab rather than forcing one. They used to be
  // SMILES-only and called setMode('smiles') on click, so clicking "ethanol"
  // while on the default IUPAC name tab flipped the tab out from under you --
  // the same "one control silently moved another" confusion the Learn/Expert
  // switch was removed for. The chip row is hidden on the Draw tab, so `mode`
  // here is only ever 'name' or 'smiles'.
  function handleExamplePick(example) {
    if (phase === 'loading') return
    const value = mode === 'name' ? example.name : example.smiles
    setSmilesInput(value)
    setValidationNote(null)
    runExplain(value)
  }

  const svgWrapperRef = useAtomHighlight(data, activePath)

  const isLoading = phase === 'loading'
  const name = data?.name
  const segments = data?.segments || []
  // NOTE: there used to be a `hasMappedParts` flag here, feeding
  // `explain-patch--success` / `--unmapped` onto the outer patch. Both class
  // names were removed from Explain.css and nothing styled them, so the flag
  // scanned every segment on every render to choose between two inert strings.
  // What a reader actually sees is the struck label on each unmapped part and
  // the ConfidenceReport rule -- neither of which needs this. If the
  // distinction is ever wanted again, it comes back together with the rule
  // that renders it.
  // All-or-nothing is a SEGMENT-level property only: a top-level part with no
  // name_range means spans could not be proven for this name at all, so the
  // whole hoverable name falls back to the plain part list. A CHILD with no
  // name_range is ordinary and expected (ethanol's suffix locant is never
  // written, caffeine's modifier locant lives inside "1H-", DDT's `chloro`
  // groups five atoms behind a span that has no room for its own `4`) -- it
  // simply renders as inert text, never as a reason to blank the page.
  const spansAvailable = segments.length > 0 && segments.every((segment) => segment.name_range)
  // IUPAC typography, read off the WHOLE name string. It has to be computed
  // here and not inside a piece, because a hover span can cut a token in half
  // -- caffeine's "1H-" is one segment's span and the italic H is inside it --
  // and half a token matches no rule. Each piece below then asks for the runs
  // that fall in its own [start, end).
  const nameStyle = name ? nameRuns(name) : []
  const activeSegment = segmentAtPath(segments, activePath)

  return (
    <>
      {/* The opening is BARE GROUND, not a card. `.page-hero` (App.css) is
          `.home-hero`'s geometry for a route that has a title instead of the
          wordmark, so the header notch meets the grey floor here exactly as
          it does on Home rather than a second white rectangle stacked under
          it. It self-insets, so it takes no `page-shell`.

          The lede is ONE sentence, which is all a hero wants. The
          instruction that used to run on after it ("...then hover any part
          of the decomposed name...") is not lost: it moved down into the
          idle empty note, which is the thing a reader is actually looking at
          while there is nothing to point at yet. */}
      <section className="page-hero" aria-label="Introduction">
        <h1 className="page-hero__title">Show the working</h1>
        <p className="page-hero__lede">
          Orthonym does not just give a molecule a name — this page shows how it got there.
        </p>
      </section>

      {/* workspace--draw flips the split so the structure editor takes the
          wide cell (see CLAUDE.md) -- Ketcher is unusable in the narrow input
          column, which is why /structure and /teach both used this modifier.
          Applied per-tab here, since the same page is narrow-input on the
          typed tabs and wide-input on Draw. */}
      <main
        className={`workspace${mode === 'draw' ? ' workspace--draw' : ''}`}
        aria-label="Explain a name"
      >
      <section className="explain-panel" aria-label="Explain a molecule">
        <form onSubmit={handleSubmit} noValidate>
          <fieldset className="explain-mode">
            <legend className="explain-mode__legend">Input</legend>
            {/* All three, always. The SMILES tab used to disappear in Learn
                mode, which meant a control in the RESULTS card could delete an
                input tab in this one -- and bump you off it mid-edit. Owner
                instruction: the three inputs apply permanently. */}
            {[
              { value: 'name', label: 'IUPAC name' },
              { value: 'smiles', label: 'SMILES' },
              { value: 'draw', label: 'Draw' },
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

          {/* The typed tabs wear `.field--framed` -- the same box /from-name
              got, label inside the frame, the focus ring on the frame rather
              than an underline. The Draw tab keeps the PLAIN `.field`: the
              editor is a bordered iframe already and a frame around a frame is
              a card in a card (DESIGN.md).
              The action row used to live INSIDE this field, which put the
              submit button inside the frame the moment the frame appeared. It
              is a sibling now, spaced by the form's own column gap. */}
          {mode === 'draw' ? (
            <div className="field">
              <span className="field__label">Draw a molecule</span>
              {editorState === 'error' ? (
                <p className="explain-panel__note" role="alert">
                  The drawing area did not load. Reload the page to try again.
                </p>
              ) : (
                <iframe
                  ref={iframeRef}
                  title="Molecule drawing area"
                  className="structure-editor"
                  src="/standalone/index.html"
                  onLoad={handleFrameLoad}
                  onError={handleFrameError}
                />
              )}
            </div>
          ) : (
            <div className="field field--framed">
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
            </div>
          )}

          <div className="explain-panel__actions">
            <button
              type={mode === 'draw' ? 'button' : 'submit'}
              className="btn btn--amber"
              onClick={mode === 'draw' ? handleDraw : undefined}
              disabled={isLoading || (mode === 'draw' && editorState !== 'ready')}
            >
              <Icon name="translate" />
              {isLoading ? 'Explaining…' : 'Explain'}
            </button>
            {validationNote && (
              <p className="explain-panel__note" role="status">
                {validationNote}
              </p>
            )}
          </div>

          {/* Hidden on the Draw tab: there is nothing to paste a chip INTO
              there, and handing a drawn-structure user a text example would
              mean silently leaving the tab to run it. */}
          {mode !== 'draw' && (
            <div className="examples" role="group" aria-label="Try a curated example">
              <span className="examples__label">Try one:</span>
              <ul className="examples__list" role="list">
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
          )}
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
          <p className="notice" role="alert">
            Could not reach Orthonym&rsquo;s backend ({fetchError}). Is it running on{' '}
            <code>localhost:8000</code>?
          </p>
        )}

        <div aria-live="polite">
          {phase === 'idle' && (
            <div className="explain-patch">
              {/* Two sentences, because the second one came DOWN from the
                  lede when the page-head card became a hero: a hero carries
                  one sentence, and "then hover any part of the name" is an
                  instruction for the panel it describes, not for the
                  masthead. Same words, moved -- no new claim. */}
              <p className="explain-patch__empty-note">
                Nothing to explain yet — type an IUPAC name or a SMILES string above, draw a
                structure, or try one of the examples. Then point at any part of the name to
                see exactly which atoms it describes.
              </p>
            </div>
          )}

          {phase === 'loading' && (
            <div className="explain-patch" aria-busy="true">
              <span className="explain-patch__state-label">Naming and decomposing&hellip;</span>
              <div className="explain-patch__pending-cloth" aria-hidden="true">
                <span className="explain-patch__pending-dash" />
                <span className="explain-patch__pending-dash" />
                <span className="explain-patch__pending-dash" />
              </div>
            </div>
          )}

          {phase === 'error' && (
            <div className="explain-patch" role="alert">
              <span className="explain-patch__state-label">
                {apiError || 'Could not explain this molecule'}
              </span>
              <div className="explain-patch__snip-wrap" aria-hidden="true">
                <span className="explain-patch__snip explain-patch__snip--a" />
                <span className="explain-patch__snip explain-patch__snip--b" />
              </div>
              {/* From tierRow, the /api/translate row fetched alongside: the
                  explain error is only a sentence, and the tier row is what
                  says whether this was an abstain or a crash (reportable) or
                  a SMILES that would not parse (not). Null in name mode. */}
              <ReportLink row={tierRow} where="Explain" settings={TIER_SETTINGS} />
            </div>
          )}

          {phase === 'success' && (
            <div className="explain-patch">
              <div className="explain-result">
                <div className="explain-result__name-row">
                  <span className="explain-result__name-label">Name</span>
                  {name && spansAvailable ? (
                    <p className="explain-result__name explain-name" aria-live="polite">
                      {sliceName(name, nameTargets(segments)).map((piece, index) => (
                        <Fragment key={index}>
                        {/* A part is one hover target, so it never wraps
                            inside; the line may break BETWEEN parts where
                            the name has a chemical boundary. */}
                        {index > 0 && /[)\]},]/.test(name[piece.start - 1] || '') &&
                          !'-,)]}'.includes(name[piece.start] || 'x') && <wbr />}
                        {piece.path === null ? (
                          <span><Pieces pieces={applyRuns(name, nameStyle, piece.start, piece.end)} /></span>
                        ) : (
                          <span
                            className={`explain-name__part${
                              segmentAtPath(segments, piece.path)?.owns_atoms === false
                                ? ' explain-name__part--ref'
                                : ''
                            }${activePath === piece.path ? ' explain-name__part--active' : ''}`}
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
                            <Pieces pieces={applyRuns(name, nameStyle, piece.start, piece.end)} breaks={false} />
                          </span>
                        )}
                        </Fragment>
                      ))}
                    </p>
                  ) : (
                    <p className="explain-result__name" aria-live="polite">
                      {name && renderAnnotatedName(name, segments, activePath, nameStyle)}
                    </p>
                  )}
                  {/* /api/explain returns the name and its decomposition but
                      no confidence tier. For a STRUCTURE the tier is a real
                      Orthonym verdict, so runExplain fetches it from
                      /api/translate alongside and it is shown here -- PRODUCT.md
                      principle 3 requires it wherever a name appears.

                      For a name the USER typed there is no verdict to report:
                      Orthonym did not produce that name, so it has no opinion on
                      whether it is a PIN. Saying so plainly is the honest
                      option; inventing a tier mark would misrepresent
                      confidence, which the product forbids. */}
                  {verdictKindFor(resultMode) === 'user-supplied' ? (
                    <p className="explain-tier-note">
                      This breakdown is of the name <em>you</em> supplied, so there is no
                      Orthonym confidence tier for it. Draw or paste a structure instead, or
                      run the molecule through{' '}
                      <Link to="/" className="about-link">
                        Translate
                      </Link>
                      , to see whether Orthonym&rsquo;s own name for it is a verified PIN, a
                      fallback, or a best effort.
                    </p>
                  ) : (
                    <ConfidenceReport row={tierRow} />
                  )}
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
                  <p className="notice" role="status">
                    {apiError}
                  </p>
                )}
                {/* A success phase can still be a molecule Orthonym would not
                    name: uranium trioxide lands here with a drawn structure and
                    an abstain tier row, not in the error branch. */}
                <ReportLink row={tierRow} where="Explain" settings={TIER_SETTINGS} />

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
                          {/* Referential parts (counting words, fusion
                              brackets, indicated H, stereo) own no atoms of
                              their own -- they point at the parent's. The
                              dotted underline in the name says so at a glance;
                              this line says it in words. Keyed on owns_atoms,
                              the same field TierLamp-style form-not-hue marks
                              read from, never on kind. */}
                          {activeSegment.owns_atoms === false && (
                            <p className="explain-detail__note">
                              Notation — it points at the parent&rsquo;s atoms, and names none of its own.
                            </p>
                          )}
                        </>
                      ) : (
                        <p className="explain-detail__hint">
                          Move your pointer across the name above to see what each part means.
                        </p>
                      )}
                    </div>
                  ) : (
                    <ul className="explain-segments" role="list" aria-label="Named parts">
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
function renderAnnotatedName(name, segments, activePath, style) {
  const segment = segmentAtPath(segments, activePath)
  const range = segment?.name_range
  // NOTHING ACTIVE IS STILL A RENDER. This used to `return name` here, which
  // is the raw string -- so on every name that reaches this fallback (spans
  // unproven, or `segments` empty, which is the partial result documented
  // above) the typography simply vanished: a von Baeyer name printed its
  // literal `^` caret, a stereodescriptor stayed roman, and the marks blinked
  // back on the moment a part was hovered and off again when it was not.
  // The highlight is the only thing a hover changes; the typography is not.
  if (!range) {
    return <Pieces pieces={applyRuns(name, style)} />
  }
  const [start, end] = range
  // The same typography, cut at the highlight's two boundaries. The square
  // brackets are this renderer's own marks, not part of the name, so they
  // stay outside the typeset run.
  return (
    <>
      <Pieces pieces={applyRuns(name, style, 0, start)} />
      <span className="explain-result__name-highlight">
        [<Pieces pieces={applyRuns(name, style, start, end)} />]
      </span>
      <Pieces pieces={applyRuns(name, style, end, name.length)} />
    </>
  )
}

export default Explain
