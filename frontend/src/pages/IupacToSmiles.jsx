import { useState } from 'react'
import { fetchStructureFromName } from '../lib/api'
import { MAX_NAMES, parseNameLines, convertNames } from '../lib/nameBatch'
import { rowsToSdf, downloadText } from '../lib/molExport'
import './IupacToSmiles.css'
import Icon from '../components/Icon'
import CopyButton from '../components/CopyButton'
import NameResultsTable from '../components/NameResultsTable'
import OpsinNote from '../components/OpsinNote'

// Curated names verified live against the real /api/iupac-to-smiles
// endpoint (OPSIN-backed) before shipping -- simple, well-known IUPAC
// names guaranteed to parse cleanly, the mirror of Home.jsx's EXAMPLES.
const EXAMPLES = [
  { label: 'ethanol', name: 'ethanol' },
  { label: 'acetic acid', name: 'acetic acid' },
  { label: 'benzene', name: 'benzene' },
]

function IupacToSmiles() {
  const [nameText, setNameText] = useState('')
  const [rows, setRows] = useState([]) // Row[] from convertNames
  const [progress, setProgress] = useState({ done: 0, total: 0 })
  const [fetchError, setFetchError] = useState(null)
  const [validationNote, setValidationNote] = useState(null)

  // Derived, not its own state: convert() below always clears `rows` and
  // sets `progress.total` to a non-zero count in the same batch before it
  // starts, and calls setRows(settled) exactly once with a NON-EMPTY array
  // when it finishes -- convertNames never returns an empty array once
  // `names.length` is non-zero (nameBatch.js: every index gets a row,
  // success or failure, and the function never rejects), so a batch where
  // every name fails still lands on 'done', not stuck on 'converting'.
  // 'idle' | 'converting' | 'done'
  const phase = rows.length > 0 ? 'done' : progress.total > 0 ? 'converting' : 'idle'

  // The one conversion path, parameterised on the text to convert rather than
  // reading `nameText` off state -- an example chip calls this in the same
  // click that calls `setNameText`, and state updates are async, so reading
  // `nameText` here would still see the value from BEFORE the click. Passing
  // the text explicitly is what lets the chip "submit through this same
  // path" without a second lookup function.
  async function convert(text) {
    if (phase === 'converting') return

    const { names, total, truncated } = parseNameLines(text)
    if (!names.length) {
      setValidationNote('Enter at least one IUPAC name (one per line) before converting.')
      return
    }
    // The extra lines stay visible in the textarea, so dropping them silently
    // would be a lie about what was converted.
    setValidationNote(
      truncated ? `${total} names pasted. Converting the first ${MAX_NAMES}.` : null
    )

    setFetchError(null)
    setProgress({ done: 0, total: names.length })
    setRows([])

    // TWO KINDS OF FAILURE, and the page has always told them apart. OPSIN
    // declining a name is a 2xx body with `error` set; a non-2xx status is a
    // THROW from fetchStructureFromName (api.js). convertNames flattens both
    // into ok:false rows, so the transport case is captured here on its way
    // past -- otherwise every non-2xx status would render the same "is the
    // backend running on localhost:8000?" notice.
    //
    // That notice is wrong for anything but a genuine network failure. This
    // page fires one GET per name (up to MAX_NAMES=25) against the shared
    // 60/min fast-path budget (nameBatch.js), so a third submission inside a
    // minute 429s BY DESIGN -- not because the backend is down. A 503 means
    // the backend is reachable but no worker has reported a live JVM
    // (jvm_guard); a 504 means the fast path timed out. `err.status` (set by
    // fetchStructureFromName) is what lets `transportNotice` below tell these
    // apart instead of accusing a healthy, merely busy or rate-limiting
    // backend of being unreachable.
    let transportError = null
    const fetchOne = async (name) => {
      try {
        return await fetchStructureFromName(name)
      } catch (err) {
        transportError = transportError || {
          message: err?.message || 'unknown network error',
          status: err?.status ?? null,
        }
        throw err
      }
    }

    const settled = await convertNames(names, {
      fetchOne,
      onProgress: (done, count) => setProgress({ done, total: count }),
    })
    setRows(settled)
    setFetchError(transportError)
  }

  function handleSubmit(event) {
    event.preventDefault()
    convert(nameText)
  }

  // Derived count, so the user sees it before submitting.
  const parsed = parseNameLines(nameText)
  const countLabel = parsed.names.length === 1 ? '1 name' : `${parsed.names.length} names`

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
          Type an IUPAC name and Orthonym parses it back into a molecule.
        </p>
      </section>

      <main className="workspace" aria-label="IUPAC to Structure">
        <section className="from-name-panel" aria-label="Convert an IUPAC name">
          {/* An outer, unstyled grid cell (`.workspace > .from-name-panel`
              strips the card chrome `.workspace > *` gives it by default)
              plus an inner `.from-name-panel__card` that now carries it
              instead -- the same split Home uses (`.input-col` wrapping
              `.workbench__input`), needed here because the info notch below
              has to sit on the grey ground outside the card's own white
              padding: its concave fillets cut a hole in a white shape to
              reveal what is BEHIND it, and there is nothing to reveal if
              the notch is nested inside the same white fill as its own
              background. */}
          <div className="from-name-panel__card">
          <form onSubmit={handleSubmit} noValidate>
            {/* BOTH classes are required: the flex column comes from the base
                `.field` (App.css:1132) and `.field--framed`'s own `gap` only applies
                to a flex box. The control inside MUST be a `.field__control`, or the
                base underline (App.css:1155) is not stripped and you get a doubled
                focus treatment against the frame's own :focus-within ring. */}
            <div className="field field--framed">
              <label htmlFor="iupac-names-input" className="field__label">
                IUPAC names &mdash; one per line
              </label>
              <textarea
                id="iupac-names-input"
                className="field__control"
                spellCheck={false}
                autoCorrect="off"
                autoCapitalize="off"
                placeholder={'ethanol\nacetic acid\nbenzene'}
                value={nameText}
                onChange={(event) => setNameText(event.target.value)}
              />
            </div>

            <div className="from-name-panel__actions">
              {/* The one primary action on this surface, and therefore the
                  one filled crimson glass button. The chips below are the
                  secondary vocabulary and stay `.chip`. */}
              <button type="submit" className="btn btn--accent" disabled={phase === 'converting'}>
                <Icon name="translate" />
                {phase === 'converting' ? 'Converting…' : 'Convert'}
              </button>
              <span className="from-name-panel__count">{countLabel}</span>
            </div>
            {validationNote && (
              <p className="from-name-panel__note" role="status">{validationNote}</p>
            )}

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
                      disabled={phase === 'converting'}
                      onClick={() => {
                        setNameText(example.name)
                        setValidationNote(null)
                        convert(example.name)
                      }}
                    >
                      {example.label}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          </form>
          </div>

          <OpsinNote />
        </section>

        <section className="from-name-results" aria-label="Structure result">
          {fetchError && (
            <p className="notice" role="alert">
              <TransportNotice error={fetchError} />
            </p>
          )}
          <div className="from-name-results__live" aria-live="polite">
            {phase === 'idle' && <IdleNote />}
            {phase === 'converting' && <ConvertProgress done={progress.done} total={progress.total} />}
            {phase === 'done' && rows.length === 1 && <SingleResult row={rows[0]} />}
            {phase === 'done' && rows.length > 1 && <NameResultsTable rows={rows} />}
          </div>
        </section>
      </main>
    </>
  )
}

// Four transport failures, one wrongly worded as "the backend is down" until
// now. This page fires one GET per name (up to MAX_NAMES=25) against the
// shared 60/min fast-path budget, so a THIRD submission inside a minute
// 429s by design (nameBatch.js) -- that is not the backend being offline,
// and telling a visitor their local server is down when it is in fact
// working exactly as designed is the wrong direction to be wrong in. A 503
// means the backend answered but no worker has a live JVM yet (jvm_guard);
// its wording below is lifted from the app's own degraded-backend copy
// (see the 503 branch) rather than invented fresh, so every surface
// describes the same backend state the same way. A 504 means the fast path
// itself timed out. Anything
// else -- including a real network failure, where `status` is null --
// keeps the original "is it running on localhost:8000?" text unchanged.
function TransportNotice({ error }) {
  if (error.status === 429) {
    return (
      <>
        Orthonym&rsquo;s request limit was hit &mdash; this page sends one request per name, and
        converting a lot of names in a short span can use it up. Wait a minute, then try again.
      </>
    )
  }
  if (error.status === 503) {
    // Wording lifted verbatim from the app's own degraded-backend copy
    // (About.jsx's Service status section: `{raw.opsin}. Naming endpoints
    // answer 503 until a worker reports one.`, backed by main.py's
    // `opsin="no worker has a live JVM"`) rather than invented fresh, so
    // every surface describes the same backend state the same way.
    return (
      <>
        Orthonym&rsquo;s backend is up, but no worker has a live JVM. Naming endpoints answer 503
        until a worker reports one.
      </>
    )
  }
  if (error.status === 504) {
    return <>This conversion took too long rather than failed. Try again in a moment.</>
  }
  return (
    <>
      Could not reach Orthonym&rsquo;s backend ({error.message}). Is it running on{' '}
      <code>localhost:8000</code>?
    </>
  )
}

function IdleNote() {
  return (
    <div className="from-name-patch from-name-patch--idle">
      <p className="from-name-patch__empty-note">
        Nothing entered here yet &mdash; type an IUPAC name above and convert to see its structure.
      </p>
    </div>
  )
}

function ConvertProgress({ done, total }) {
  const percent = total ? Math.round((done / total) * 100) : 0
  return (
    <div className="from-name-progress" role="status" aria-live="polite">
      <div className="from-name-progress__head">
        <span className="from-name-progress__label">
          Reading {total === 1 ? 'the name' : `${total} names`}
        </span>
        <span className="from-name-progress__count">{done} of {total}</span>
      </div>
      {/* A REAL percentage, unlike Home's indeterminate stripe: Home blocks on
          one server call that reports nothing until it finishes, whereas this
          loop runs in the browser and genuinely knows how many are done. */}
      <div
        className="from-name-progress__track"
        role="progressbar"
        aria-valuenow={done}
        aria-valuemin={0}
        aria-valuemax={total}
      >
        <div className="from-name-progress__fill" style={{ width: `${percent}%` }} />
      </div>
    </div>
  )
}

function SingleResult({ row }) {
  if (!row.ok) {
    return (
      <div className="from-name-patch" role="alert">
        <div className="from-name-patch__top">
          <span className="from-name-patch__state-label">
            {row.error || 'Could not parse this name'}
          </span>
        </div>
        {/* The shipped failure mark: two struck rules, no colour. */}
        <div className="from-name-patch__snip-wrap" aria-hidden="true">
          <span className="from-name-patch__snip from-name-patch__snip--a" />
          <span className="from-name-patch__snip from-name-patch__snip--b" />
        </div>
      </div>
    )
  }
  const d = row.data
  return (
    <div className="from-name-patch from-name-patch--success">
      <div className="from-name-patch__top">
        <span className="from-name-patch__state-label">Parsed successfully</span>
      </div>
      {/* Two columns: the picture and the strings it stands for. They are two
          different kinds of content and reading one does not mean reading the
          other, so they sit side by side rather than stacked -- which also stops
          the depiction band eating a full card-width row of empty grey. */}
      <div className="from-name-split">
        <div className="from-name-split__figure">
          {d.depiction_svg && (
            <div className="from-name-patch__depiction">
              <img src={d.depiction_svg} alt={`2D structure depiction for "${row.name}"`} />
            </div>
          )}
        </div>

        <div className="from-name-split__data">
          <dl className="idlist">
            <IdRow label="SMILES (OPSIN)" value={d.smiles} />
            <IdRow label="SMILES (canonical)" value={d.canonical_smiles} />
            <IdRow label="InChI" value={d.inchi} />
            <IdRow label="InChIKey" value={d.inchikey} />
          </dl>
          <div className="from-name-patch__downloads">
            <button
              type="button"
              className="btn btn--pastel btn--sm"
              disabled={!d.molblock}
              onClick={() =>
                downloadText(
                  `${sdfFilename(row.name)}.sdf`,
                  rowsToSdf([row]).text,
                  'chemical/x-mdl-sdfile'
                )
              }
            >
              <Icon name="download" />
              Download SDF
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

function IdRow({ label, value }) {
  return (
    <div className="idlist__row">
      <dt className="idlist__label">{label}</dt>
      <dd className="idlist__value">
        {/* An em dash, never an empty row: a missing identifier is a fact about
            the molecule and should look like one. */}
        {value ? <code>{value}</code> : <span className="idlist__none">—</span>}
        {value && <CopyButton text={value} label={`Copy ${label}`} />}
      </dd>
    </div>
  )
}

// A filename, not a name: IUPAC names carry commas, brackets, primes and
// slashes, and a slash in particular is not a legal filename character on any
// platform. Falls back to 'structure' when nothing survives.
function sdfFilename(name) {
  return name.replace(/[^a-zA-Z0-9._-]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 60) || 'structure'
}

export default IupacToSmiles
