import { useRef, useState } from 'react'
import { checkName } from '../lib/api'
import { latestOnly } from '../lib/batchJob'
import useShareLink from '../lib/useShareLink'
import Icon from '../components/Icon'
import OpsinWarnings from '../components/OpsinWarnings'
import ShareButton from '../components/ShareButton'
import Tile from '../components/Tile'
import TransportNotice from '../components/TransportNotice'
import ChemName from '../components/Typeset'
import './Check.css'

// One pair per verdict a reader is likely to meet, measured live: the same
// molecule, a different one, and the wrong enantiomer.
const EXAMPLES = [
  { label: 'ethanol', smiles: 'CCO', name: 'ethanol' },
  { label: 'aspirin, wrong name', smiles: 'CC(=O)Oc1ccccc1C(=O)O', name: '2-hydroxybenzoic acid' },
  { label: 'L-alanine, wrong stereo', smiles: 'C[C@@H](C(=O)O)N', name: '(2R)-2-aminopropanoic acid' },
]

// The verdict is about STRUCTURE only. It borrows no tier and no tier colour:
// the engine's own tier sits below it, in the tile Home uses.
function Verdict({ result, smiles }) {
  const unreadable = result.verdict === 'unreadable'
  return (
    <div className="check-verdict">
      <div className="check-verdict__head">
        <p className={`check-verdict__text check-verdict__text--${result.verdict}`}>{result.verdict_text}</p>
        <ShareButton fields={{ smiles, name: result.name }} />
      </div>
      <p className="check-verdict__how">
        {unreadable
          ? 'OPSIN could not read this name, so there is no structure to compare.'
          : 'OPSIN read your name; the two structures were compared by InChIKey.'}
      </p>
      <OpsinWarnings warnings={result.warnings} />
      <div className="check-verdict__figures">
        <figure className="check-figure">
          {/* From the answer, not a GET /api/depict?smiles=: that would put the
              structure in the access log (Privacy.jsx). */}
          {result.input_svg && <img src={result.input_svg} alt="2D structure of your SMILES" />}
          <figcaption>Your structure</figcaption>
        </figure>
        {!unreadable && (
          <figure className="check-figure">
            {result.claimed_svg && (
              <img src={result.claimed_svg} alt={`2D structure OPSIN reads from "${result.name}"`} />
            )}
            <figcaption>
              What <ChemName name={result.name} /> describes
            </figcaption>
          </figure>
        )}
      </div>
    </div>
  )
}

function Check() {
  const [smiles, setSmiles] = useState('')
  const [name, setName] = useState('')
  const [phase, setPhase] = useState('idle') // idle | loading | done
  const [result, setResult] = useState(null)
  const [fetchError, setFetchError] = useState(null)
  const [note, setNote] = useState(null)
  const track = useRef(latestOnly())

  async function run(s, n) {
    const pair = { smiles: s.trim(), name: n.trim() }
    if (!pair.smiles || !pair.name) {
      setNote('Enter both a SMILES and a name.')
      return
    }
    setNote(null)
    setFetchError(null)
    setPhase('loading')
    try {
      const { stale, value } = await track.current(checkName(pair.smiles, pair.name))
      if (stale) return
      setResult({ ...value, name: pair.name, smiles: pair.smiles })
      setPhase('done')
    } catch (err) {
      setResult(null)
      setPhase('idle')
      // A 400 is the parser's own reason the SMILES cannot be read: say it
      // beside the field, not as a server failure.
      if (err.status === 400) setNote(err.message)
      else setFetchError(err)
    }
  }

  useShareLink((fields) => {
    if (!fields.smiles || !fields.name) return
    setSmiles(fields.smiles)
    setName(fields.name)
    run(fields.smiles, fields.name)
  })

  function handleSubmit(event) {
    event.preventDefault()
    run(smiles, name)
  }

  const busy = phase === 'loading'

  return (
    <>
      <section className="page-hero" aria-label="Introduction">
        <h1 className="page-hero__title">Check a name</h1>
        <p className="page-hero__lede">
          Paste a structure and the name it was given. Orthonym says whether the name describes it.
        </p>
      </section>

      <main className="workspace check" aria-label="Check a name">
        <section className="check-panel" aria-label="Structure and name">
          <form onSubmit={handleSubmit} noValidate>
            <div className="field field--framed">
              <label htmlFor="check-smiles" className="field__label">
                Structure (SMILES)
              </label>
              <input
                id="check-smiles"
                className="field__control"
                spellCheck={false}
                autoCorrect="off"
                autoCapitalize="off"
                placeholder="CCO"
                value={smiles}
                onChange={(event) => setSmiles(event.target.value)}
              />
            </div>
            <div className="field field--framed">
              <label htmlFor="check-name" className="field__label">
                Claimed IUPAC name
              </label>
              <input
                id="check-name"
                className="field__control"
                spellCheck={false}
                autoCorrect="off"
                autoCapitalize="off"
                placeholder="ethanol"
                value={name}
                onChange={(event) => setName(event.target.value)}
              />
            </div>

            <div className="check-panel__actions">
              <button type="submit" className="btn btn--accent" disabled={busy}>
                <Icon name="translate" />
                {busy ? 'Checking…' : 'Check'}
              </button>
            </div>
            {note && (
              <p className="check-panel__note" role="status">
                {note}
              </p>
            )}

            <div className="examples" role="group" aria-label="Try a curated example">
              <span className="examples__label">Try one:</span>
              <ul className="examples__list" role="list">
                {EXAMPLES.map((example) => (
                  <li key={example.label}>
                    <button
                      type="button"
                      className="chip"
                      disabled={busy}
                      onClick={() => {
                        setSmiles(example.smiles)
                        setName(example.name)
                        run(example.smiles, example.name)
                      }}
                    >
                      {example.label}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          </form>
        </section>

        <section className="check-results" aria-label="Result" aria-live="polite" aria-busy={busy}>
          {fetchError && (
            <p className="notice" role="alert">
              <TransportNotice error={fetchError} />
            </p>
          )}
          {phase === 'idle' && !fetchError && (
            <p className="check-results__empty">
              Nothing checked yet. The answer compares structures only: a name can describe the
              right molecule and still not be its preferred IUPAC name.
            </p>
          )}
          {busy && <p className="check-results__empty">Reading the name…</p>}
          {phase === 'done' && result && (
            <>
              <Verdict result={result} smiles={result.smiles} />
              <h2 className="check-results__engine">Orthonym&rsquo;s own name for this structure</h2>
              <ul className="sampler" role="list">
                <Tile row={result.engine} phase="done" />
              </ul>
            </>
          )}
        </section>
      </main>
    </>
  )
}

export default Check
