import { useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchStructureFromName } from '../lib/api'
import './IupacToSmiles.css'
import Icon from '../components/Icon'

// Curated names verified live against the real /api/iupac-to-smiles
// endpoint (OPSIN-backed) before shipping -- simple, well-known IUPAC
// names guaranteed to parse cleanly, the mirror of Home.jsx's EXAMPLES.
const EXAMPLES = [
  { label: 'ethanol', name: 'ethanol' },
  { label: 'acetic acid', name: 'acetic acid' },
  { label: 'benzene', name: 'benzene' },
]

// phase: 'idle' (nothing submitted yet) | 'loading' (request in flight) |
// 'success' (OPSIN resolved a structure) | 'error' (OPSIN/the API
// declined -- a normal 2xx response with `error` set, not a network fault)
function IupacToSmiles() {
  const [nameInput, setNameInput] = useState('')
  const [phase, setPhase] = useState('idle')
  const [resolvedName, setResolvedName] = useState(null)
  const [smiles, setSmiles] = useState(null)
  const [depictionSvg, setDepictionSvg] = useState(null)
  const [apiError, setApiError] = useState(null)
  const [fetchError, setFetchError] = useState(null)
  const [validationNote, setValidationNote] = useState(null)

  function runLookup(name) {
    setFetchError(null)
    setPhase('loading')

    fetchStructureFromName(name)
      .then((data) => {
        setResolvedName(name)
        if (data.error) {
          setApiError(data.error)
          setSmiles(null)
          setDepictionSvg(null)
          setPhase('error')
        } else {
          setSmiles(data.smiles)
          setDepictionSvg(data.depiction_svg)
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

    const trimmed = nameInput.trim()
    if (!trimmed) {
      setValidationNote('Enter an IUPAC name before converting.')
      return
    }
    setValidationNote(null)
    runLookup(trimmed)
  }

  function handleExamplePick(example) {
    if (phase === 'loading') return
    setNameInput(example.name)
    setValidationNote(null)
    runLookup(example.name)
  }

  const isLoading = phase === 'loading'

  return (
    <>
      {/* The opening is NOT a card. `.page-hero` (App.css) is `.home-hero`'s
          geometry for a route that has a title instead of the wordmark: no
          fill, no border, no shadow, no radius, so the page begins with the
          grey ground rather than with a second white rectangle under the
          header notch. It self-insets, so it must not also take `page-shell`.
          The lede is ONE sentence by design. The rest of what the old
          `.page-head` lede said -- the SMILES + depiction output, and OPSIN's
          name -- moved down into the input card, where it sits beside the
          control it describes. Nothing new is claimed here. */}
      <section className="page-hero" aria-label="Introduction">
        <h1 className="page-hero__title">Read the name back</h1>
        <p className="page-hero__lede">
          Type an IUPAC name and STITCH parses it back into a molecule.
        </p>
      </section>

      <main className="workspace" aria-label="IUPAC to Structure">
        <section className="from-name-panel" aria-label="Convert an IUPAC name">
          <form onSubmit={handleSubmit} noValidate>
            <div className="field">
              <label htmlFor="iupac-name-input" className="field__label">
                IUPAC name
              </label>
              <input
                id="iupac-name-input"
                type="text"
                className="field__control"
                spellCheck={false}
                autoCorrect="off"
                autoCapitalize="off"
                placeholder="e.g. ethanol"
                value={nameInput}
                onChange={(event) => setNameInput(event.target.value)}
              />
              <div className="from-name-panel__actions">
                {/* The one primary action on this surface, and therefore the
                    one filled crimson glass button. The chips below are the
                    secondary vocabulary and stay `.chip`. */}
                <button type="submit" className="btn btn--accent" disabled={isLoading}>
                  <Icon name="translate" />
                  {isLoading ? 'Converting…' : 'Convert'}
                </button>
                {validationNote && (
                  <p className="from-name-panel__note" role="status">
                    {validationNote}
                  </p>
                )}
              </div>
            </div>

            <div className="examples" role="group" aria-label="Try a curated example">
              <span className="examples__label">Try one:</span>
              {/* role="list" because index.css strips list semantics globally
                  (`list-style: none` with no role), which silently drops the
                  list from the accessibility tree in Safari/VoiceOver. */}
              <ul className="examples__list" role="list">
                {EXAMPLES.map((example) => (
                  <li key={example.name}>
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

          {/* The card's foot: what you get and who parsed it, then the shared
              pointer to About. One hairline divider INSIDE the card, which is
              the only place a seam survives in this system. */}
          <div className="from-name-panel__foot">
            <p className="prose-sm">
              You get a SMILES string plus a 2D depiction, read by OPSIN &mdash; an
              independent name-to-structure parser.
            </p>
            <p className="page-about-note">
              Read how this works, and STITCH&rsquo;s measured accuracy, on the{' '}
              <Link to="/about" className="about-link">
                About
              </Link>{' '}
              page.
            </p>
          </div>
        </section>

        <section className="from-name-results" aria-label="Structure result">
          {fetchError && (
            <p className="notice" role="alert">
              Could not reach STITCH&rsquo;s backend ({fetchError}). Is it running on{' '}
              <code>localhost:8000</code>?
            </p>
          )}

          {/* The live region is also the flex track the depiction grows in:
              it takes the height the card has left, so the drawing is as
              large as the cell genuinely allows and never larger. */}
          <div className="from-name-results__live" aria-live="polite">
            {phase === 'idle' && (
              <div className="from-name-patch from-name-patch--idle">
                <p className="from-name-patch__empty-note">
                  Nothing entered here yet &mdash; type an IUPAC name above and convert to see its
                  structure.
                </p>
              </div>
            )}

            {phase === 'loading' && (
              <div className="from-name-patch" aria-busy="true">
                <div className="from-name-patch__top">
                  <span className="from-name-patch__state-label">Converting&hellip;</span>
                </div>
                <div className="from-name-patch__pending-cloth" aria-hidden="true">
                  <span className="from-name-patch__pending-dash" />
                  <span className="from-name-patch__pending-dash" />
                  <span className="from-name-patch__pending-dash" />
                </div>
              </div>
            )}

            {phase === 'success' && (
              <div className="from-name-patch from-name-patch--success">
                <div className="from-name-patch__top">
                  <span className="from-name-patch__state-label">Parsed successfully</span>
                </div>
                <div className="from-name-patch__body">
                  <div className="from-name-patch__field">
                    <span className="from-name-patch__field-label">SMILES</span>
                    <code className="from-name-patch__smiles">{smiles}</code>
                  </div>
                  {depictionSvg && (
                    <div className="from-name-patch__depiction">
                      <img src={depictionSvg} alt={`2D structure depiction for "${resolvedName}"`} />
                    </div>
                  )}
                </div>
              </div>
            )}

            {phase === 'error' && (
              <div className="from-name-patch" role="alert">
                <div className="from-name-patch__top">
                  <span className="from-name-patch__state-label">
                    {apiError || 'Could not parse this name'}
                  </span>
                </div>
                <div className="from-name-patch__snip-wrap" aria-hidden="true">
                  <span className="from-name-patch__snip from-name-patch__snip--a" />
                  <span className="from-name-patch__snip from-name-patch__snip--b" />
                </div>
              </div>
            )}
          </div>
        </section>
      </main>
    </>
  )
}

export default IupacToSmiles
