import { useState } from 'react'
import { Link } from 'react-router-dom'
import ExplainView from '../components/ExplainView'
import useExplain, { TIER_SETTINGS } from '../lib/useExplain'
import { useKetcher } from '../lib/useKetcher'
import './Explain.css'
import Icon from '../components/Icon'
import ReportLink from '../components/ReportLink'
import useShareLink from '../lib/useShareLink'
import TransportNotice from '../components/TransportNotice'

// Curated structures spanning what the decomposition really does now that
// it comes from OPSIN's own parse tree rather than SMARTS rules: a simple
// parent + suffix (ethanol), a molecule whose internal symmetry makes some
// parts genuinely unmappable so those parts keep their text but light no
// atoms (ibuprofen), and a bare ring parent with no principal
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
  const { phase, data, apiError, fetchError, tierRow, resultMode, shareFields, run } = useExplain()
  const [validationNote, setValidationNote] = useState(null)
  // enabled only on the Draw tab: the iframe does not exist otherwise, and an
  // armed readiness clock would time out against nothing and report the editor
  // broken before the user ever opened it.
  const { iframeRef, editorState, handleFrameLoad, handleFrameError, getKetcher } =
    useKetcher({ enabled: mode === 'draw' })

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

  // A share link is explained on arrival; a name wins over a SMILES when a
  // link carries both.
  useShareLink((fields) => {
    const linkMode = fields.name ? 'name' : fields.smiles ? 'smiles' : null
    if (!linkMode) return
    const value = fields[linkMode].trim()
    setMode(linkMode)
    setSmilesInput(value)
    runExplain(value, linkMode)
  })

  // requestMode defaults to the current tab, but a caller whose tab does not
  // NAME an endpoint must pass one explicitly. `handleDraw` is that caller: a
  // drawing is a structure once Ketcher hands back its SMILES, so it asks for
  // 'smiles' while `mode` still reads 'draw'. (setMode() is not visible to
  // this function's `mode` closure until the next render, so a caller that
  // sets the tab in the same tick must pass one too.)
  function runExplain(value, requestMode = mode) {
    run(value, requestMode)
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

  // The chips FOLLOW the current tab rather than forcing one: clicking "ethanol"
  // on the IUPAC name tab must not flip the tab. The chip row is hidden on the
  // Draw tab, so `mode` here is only ever 'name' or 'smiles'.
  function handleExamplePick(example) {
    if (phase === 'loading') return
    const value = mode === 'name' ? example.name : example.smiles
    setSmilesInput(value)
    setValidationNote(null)
    runExplain(value)
  }

  const isLoading = phase === 'loading'

  return (
    <>
      {/* The opening is BARE GROUND, not a card. `.page-hero` (App.css) is
          `.home-hero`'s geometry for a route that has a title instead of the
          wordmark, so the header notch meets the grey floor here exactly as
          it does on Home rather than a second white rectangle stacked under
          it. It self-insets, so it takes no `page-shell`.

          The lede is ONE sentence, which is all a hero wants; the hover
          instruction lives in the idle empty note, which is what a reader is
          looking at while there is nothing to point at yet. */}
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
            {/* All three inputs, always: a control in the results card must not
                delete an input tab (owner instruction). */}
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
              The action row is a sibling of the field, not inside the frame,
              spaced by the form's own column gap. */}
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
            <TransportNotice error={fetchError} />
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
              {/* A failure is a sentence ("OPSIN reads this name in a reordered form ..."),
                  so it is set in sentence case; the uppercase caption style is for the
                  one-word pending label above. */}
              <span className="explain-patch__state-label explain-patch__state-label--sentence">
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
              <ExplainView
                key={`${resultMode}:${data?.smiles}:${data?.name}`}
                data={data}
                resultMode={resultMode}
                tierRow={tierRow}
                apiError={apiError}
                shareFields={shareFields}
              />
            </div>
          )}
        </div>
      </section>
      </main>
    </>
  )
}

export default Explain
