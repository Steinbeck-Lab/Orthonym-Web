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
      <div className="page-head page-shell">
        <h1 className="page-head__title">Read the name back</h1>
        <p className="page-head__lede">
          Type an IUPAC name and Orthonym parses it back into a molecule &mdash; a SMILES string
          plus a 2D depiction &mdash; using OPSIN, an independent name-to-structure parser.
        </p>
      </div>

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
                <button type="submit" className="btn" disabled={isLoading}>
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
              <ul className="examples__list">
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

          <p className="page-about-note">
            Read how this works, and Orthonym&rsquo;s measured accuracy, on the{' '}
            <Link to="/about" className="about-link">
              About
            </Link>{' '}
            page.
          </p>
        </section>

        <section className="from-name-results" aria-label="Structure result">
          {fetchError && (
            <p className="from-name-fetch-error" role="alert">
              Could not reach Orthonym&rsquo;s backend ({fetchError}). Is it running on{' '}
              <code>localhost:8000</code>?
            </p>
          )}

          <div aria-live="polite">
            {phase === 'idle' && (
              <div className="from-name-patch from-name-patch--idle">
                <p className="from-name-patch__empty-note">
                  Nothing entered here yet &mdash; type an IUPAC name above and convert to see its
                  structure.
                </p>
              </div>
            )}

            {phase === 'loading' && (
              <div className="from-name-patch from-name-patch--loading" aria-busy="true">
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
              <div className="from-name-patch from-name-patch--error" role="alert">
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
