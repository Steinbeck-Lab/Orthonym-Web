import { useRef, useState } from 'react'
import { checkName, createJob, parsePreview } from '../lib/api'
import { jobEntryFromEnvelope, latestOnly } from '../lib/batchJob'
import { verdictHow } from '../lib/verdicts'
import useShareLink from '../lib/useShareLink'
import BatchResults from '../components/BatchResults'
import ChoicePills from '../components/ChoicePills'
import Dropzone from '../components/Dropzone'
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

// What the engine half of /api/name-check is named with (tasks.check_name:
// best effort on, OPSIN verify on, salts kept), for "Report SMILES on GitHub".
const CHECK_SETTINGS = { bestEffort: true, verify: true, stripSalts: false }

// The verdict is about STRUCTURE only. It borrows no tier and no tier colour:
// the engine's own tier sits below it, in the tile Home uses.
function Verdict({ result }) {
  const unreadable = result.verdict === 'unreadable'
  return (
    <div className="check-verdict">
      <div className="check-verdict__head">
        <p className="check-verdict__text">{result.verdict_text}</p>
        <ShareButton fields={{ smiles: result.smiles, name: result.name }} />
      </div>
      <p className="panel-note">
        {verdictHow(result)}
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
  // The note under each form, in an always-mounted live region. `n` keys the
  // message's node, so the same sentence twice is a new node and is read again.
  const [noteState, setNoteState] = useState({ text: null, n: 0 })
  const note = noteState.text
  const setNote = (text) => setNoteState((prev) => ({ text, n: prev.n + 1 }))
  // The fields a failed submit was about (aria-invalid; the note describes
  // them): any of 'smiles', 'name', 'file'.
  const [invalid, setInvalid] = useState([])
  const smilesRef = useRef(null)
  const nameRef = useRef(null)
  const track = useRef(latestOnly())
  // The file preview's own guard: picking file A then B must never leave A's
  // count beside B, or a count after Remove.
  const trackPreview = useRef(latestOnly())
  // 'pair' checks one SMILES and name; 'file' starts a name-check job from a
  // smiles,name CSV, shown in the batch table with a verdict column.
  const [mode, setMode] = useState('pair')
  const [file, setFile] = useState(null)
  const [preview, setPreview] = useState(null)
  const [job, setJob] = useState(null)
  const [starting, setStarting] = useState(false)
  const [announcement, setAnnouncement] = useState('')

  async function startJob(event) {
    event.preventDefault()
    // aria-disabled, not disabled, on the submit button: the guard is here.
    if (starting) return
    if (!file) {
      setNote('Choose a CSV with a smiles column and a name column.')
      setInvalid(['file'])
      document.getElementById('check-file')?.focus()
      return
    }
    setInvalid([])
    setNote(null)
    setStarting(true)
    try {
      const envelope = await createJob({ file, kind: 'check' })
      // Not remembered in jobStore: that list is Home's to restore.
      // A new job replaces the file: one file, one run.
      setFile(null)
      setPreview(null)
      setJob(jobEntryFromEnvelope(envelope))
    } catch (err) {
      // The server's own sentence: no name column, too many rows, a busy cap.
      setNote(err?.message || 'Could not start the check.')
    } finally {
      setStarting(false)
    }
  }

  async function run(s, n) {
    const pair = { smiles: s.trim(), name: n.trim() }
    if (!pair.smiles || !pair.name) {
      setNote('Enter both a SMILES and a name.')
      const empty = [!pair.smiles && 'smiles', !pair.name && 'name'].filter(Boolean)
      setInvalid(empty)
      // The form is noValidate: focus goes to the first field to fill in.
      ;(empty[0] === 'smiles' ? smilesRef : nameRef).current?.focus()
      return
    }
    setInvalid([])
    setNote(null)
    setFetchError(null)
    setPhase('loading')
    try {
      const { stale, value } = await track.current(checkName(pair.smiles, pair.name))
      if (stale) return
      setResult({ ...value, name: pair.name, smiles: pair.smiles })
      setPhase('done')
      setAnnouncement(`Checked: ${value.verdict_text}`)
    } catch (err) {
      setResult(null)
      setPhase('idle')
      // A 400 is the parser's own reason the SMILES cannot be read: say it
      // beside the field, not as a server failure.
      setAnnouncement('')
      if (err.status === 400) {
        setNote(err.message)
        setInvalid(['smiles'])
      } else setFetchError(err)
    }
  }

  useShareLink((fields) => {
    if (!fields.smiles || !fields.name) return
    setSmiles(fields.smiles)
    setName(fields.name)
    run(fields.smiles, fields.name)
  })

  const busy = phase === 'loading'

  function handleSubmit(event) {
    event.preventDefault()
    // aria-disabled, not disabled, on Check: the guard is here.
    if (busy) return
    run(smiles, name)
  }

  const describe = (field) => (invalid.includes(field) ? 'check-note-pair' : undefined)

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
          <ChoicePills
            name="check-mode"
            label="What to check"
            options={[
              ['pair', 'One pair'],
              ['file', 'Upload CSV'],
            ]}
            value={mode}
            onChange={(value) => {
              setMode(value)
              setNote(null)
              setInvalid([])
            }}
            disabled={busy || starting}
          />

          {mode === 'file' ? (
            <form onSubmit={startJob} noValidate>
              <Dropzone
                inputId="check-file"
                file={file}
                preview={preview}
                onFile={async (chosen) => {
                  setFile(chosen)
                  setPreview(null)
                  setNote(null)
                  setInvalid([])
                  if (!chosen) {
                    trackPreview.current(Promise.resolve(null))
                    return
                  }
                  try {
                    const { stale, value } = await trackPreview.current(parsePreview({ file: chosen }))
                    if (!stale) setPreview(value)
                  } catch (err) {
                    setNote(`Could not read that file: ${err?.message ?? 'unknown error'}`)
                  }
                }}
                onRemove={() => {
                  // Retires any preview still in flight for the removed file.
                  trackPreview.current(Promise.resolve(null))
                  setFile(null)
                  setPreview(null)
                }}
                onReject={setNote}
                disabled={starting}
                invalid={invalid.includes('file')}
                describedBy={invalid.includes('file') ? 'check-note-file' : undefined}
              />
              <p className="panel-note">
                A CSV with a <code>smiles</code> column and a <code>name</code> column; an{' '}
                <code>id</code> column is optional. Each row with a readable SMILES and a one-line
                name gets a verdict and Orthonym&rsquo;s own name.
              </p>
              <div className="check-panel__actions">
                {/* aria-disabled, not disabled (startJob guards): a button
                    disabled under the focus drops it to <body>. Without a
                    file it stays pressable and says what is missing. */}
                <button
                  type="submit"
                  className="btn btn--accent"
                  aria-disabled={starting || !file || undefined}
                >
                  <Icon name="upload" />
                  {starting ? 'Starting…' : 'Check every row'}
                </button>
              </div>
              <p className="check-panel__note" id="check-note-file" role="status">
                {note && <span key={noteState.n}>{note}</span>}
              </p>
            </form>
          ) : (
          <form onSubmit={handleSubmit} noValidate>
            <div className="field field--framed">
              <label htmlFor="check-smiles" className="field__label">
                Structure (SMILES)
              </label>
              <input
                id="check-smiles"
                ref={smilesRef}
                aria-invalid={invalid.includes('smiles') || undefined}
                aria-describedby={describe('smiles')}
                className="field__control"
                spellCheck={false}
                autoCorrect="off"
                autoCapitalize="off"
                placeholder="CCO"
                value={smiles}
                onChange={(event) => {
                  setSmiles(event.target.value)
                  if (invalid.length) setInvalid([])
                }}
              />
            </div>
            <div className="field field--framed">
              <label htmlFor="check-name" className="field__label">
                Claimed IUPAC name
              </label>
              <input
                id="check-name"
                ref={nameRef}
                aria-invalid={invalid.includes('name') || undefined}
                aria-describedby={describe('name')}
                className="field__control"
                spellCheck={false}
                autoCorrect="off"
                autoCapitalize="off"
                placeholder="ethanol"
                value={name}
                onChange={(event) => {
                  setName(event.target.value)
                  if (invalid.length) setInvalid([])
                }}
              />
            </div>

            <div className="check-panel__actions">
              <button type="submit" className="btn btn--accent" aria-disabled={busy || undefined}>
                <Icon name="translate" />
                {busy ? 'Checking…' : 'Check'}
              </button>
            </div>
            <p className="check-panel__note" id="check-note-pair" role="status">
              {note && <span key={noteState.n}>{note}</span>}
            </p>

            <div className="examples" role="group" aria-label="Try a curated example">
              <span className="examples__label">Try one:</span>
              <ul className="examples__list" role="list">
                {EXAMPLES.map((example) => (
                  <li key={example.label}>
                    <button
                      type="button"
                      className="chip"
                      aria-disabled={busy || undefined}
                      onClick={() => {
                        // A chip pressed is focused; disabling it would
                        // drop that focus, so it refuses here instead.
                        if (busy) return
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
          )}
        </section>

        {mode === 'file' ? (
          <section className={`check-results${job ? ' workspace__bare' : ''}`} aria-label="Checked rows">
            {job ? (
              <BatchResults key={job.jobId} job={job} persist={false} onForget={() => setJob(null)} />
            ) : (
              <p className="check-results__empty">
                No file checked yet. Each row is compared on structure only: a name can describe the
                right molecule and still not be its preferred IUPAC name.
              </p>
            )}
          </section>
        ) : (
        // Not a live region: the whole verdict, figures and tile would be read
        // out. The one-line status below says what came back.
        <section className="check-results" aria-label="Result" aria-busy={busy}>
          <p className="sr-only" role="status">
            {announcement}
          </p>
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
              <Verdict result={result} />
              <h2 className="check-results__engine">Orthonym&rsquo;s own name for this structure</h2>
              <ul className="sampler" role="list">
                <Tile row={result.engine} phase="done" where="Check" settings={CHECK_SETTINGS} />
              </ul>
            </>
          )}
        </section>
        )}
      </main>
    </>
  )
}

export default Check
