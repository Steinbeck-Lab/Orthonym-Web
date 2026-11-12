import { useRef, useState } from 'react'
import ChoicePills from '../components/ChoicePills'
import ExplainView from '../components/ExplainView'
import Icon from '../components/Icon'
import ReportLink from '../components/ReportLink'
import ShareButton from '../components/ShareButton'
import TransportNotice from '../components/TransportNotice'
import { compareMarks, compareShareFields } from '../lib/compareNodes'
import useExplain, { TIER_SETTINGS } from '../lib/useExplain'
import useShareLink from '../lib/useShareLink'
// Explain.css styles ExplainView.
import './Explain.css'
import './Compare.css'

const EXAMPLES = [
  { label: 'propan-1-ol vs propan-2-ol', a: 'propan-1-ol', b: 'propan-2-ol' },
  { label: '2-methyl vs 2,2-dimethylbutane', a: '2-methylbutane', b: '2,2-dimethylbutane' },
]

// One side's input: a name or a SMILES, its own toggle.
function SideInput({ id, label, value, onValue, mode, onMode, invalid, noteId, inputRef }) {
  return (
    <div className="compare-input">
      <div className="compare-input__head">
        <span className="compare-input__label">{label}</span>
        <ChoicePills
          name={`${id}-mode`}
          label={`${label}: name or SMILES`}
          options={[
            ['name', 'Name'],
            ['smiles', 'SMILES'],
          ]}
          value={mode}
          onChange={onMode}
        />
      </div>
      <div className="field field--framed">
        <label htmlFor={id} className="field__label">
          {mode === 'name' ? 'IUPAC name' : 'Structure (SMILES)'}
        </label>
        <input
          id={id}
          ref={inputRef}
          aria-invalid={invalid || undefined}
          aria-describedby={invalid ? noteId : undefined}
          className="field__control"
          spellCheck={false}
          autoCorrect="off"
          autoCapitalize="off"
          placeholder={mode === 'name' ? 'propan-1-ol' : 'CCCO'}
          value={value}
          onChange={(event) => onValue(event.target.value)}
        />
      </div>
    </div>
  )
}

// One side's answer, in /explain's own states. Each side has its own
// useExplain, so each has its own stale-reply guard.
function SideResult({ label, explain, marks }) {
  const { phase, data, apiError, fetchError, tierRow, tierState, resultMode } = explain
  return (
    <section className="compare-side" aria-label={`${label}: explanation`} aria-busy={phase === 'loading'}>
      <h2 className="compare-side__label">{label}</h2>
      {fetchError && (
        <p className="notice" role="alert">
          <TransportNotice error={fetchError} />
        </p>
      )}
      {phase === 'idle' && !fetchError && <p className="panel-note">Nothing here yet.</p>}
      {phase === 'loading' && <p className="panel-note">Naming and decomposing…</p>}
      {phase === 'error' && (
        <div role="alert">
          <p className="panel-note">{apiError || 'Could not explain this molecule'}</p>
          <ReportLink row={tierRow} where="Compare" settings={TIER_SETTINGS} />
        </div>
      )}
      {phase === 'success' && (
        <ExplainView
          key={`${resultMode}:${data?.smiles}:${data?.name}`}
          data={data}
          resultMode={resultMode}
          tierRow={tierRow}
          tierState={tierState}
          apiError={apiError}
          marks={marks}
        />
      )}
    </section>
  )
}

function Compare() {
  const [a, setA] = useState('')
  const [b, setB] = useState('')
  const [modeA, setModeA] = useState('name')
  const [modeB, setModeB] = useState('name')
  const [note, setNote] = useState(null)
  // Which side an empty submit refused: { a, b } or null.
  const [empty, setEmpty] = useState(null)
  const refA = useRef(null)
  const refB = useRef(null)
  const left = useExplain()
  const right = useExplain()
  const busy = left.phase === 'loading' || right.phase === 'loading'

  function compare(va, vb, ma = modeA, mb = modeB) {
    const x = va.trim()
    const y = vb.trim()
    if (!x || !y) {
      const message = 'Enter something on both sides.'
      setEmpty({ a: !x, b: !y })
      // One live region, always mounted: the same sentence twice is cleared
      // first, or a screen reader would not read it again.
      if (note === message) {
        setNote(null)
        requestAnimationFrame(() => setNote(message))
      } else {
        setNote(message)
      }
      // Focus goes to the empty field, which reads the note as its description.
      const firstEmpty = x ? refB : refA
      firstEmpty.current?.focus()
      return
    }
    setEmpty(null)
    setNote(null)
    left.run(x, ma)
    right.run(y, mb)
  }

  useShareLink((fields) => {
    if (!fields.a || !fields.b) return
    const ma = fields.am === 'smiles' ? 'smiles' : 'name'
    const mb = fields.bm === 'smiles' ? 'smiles' : 'name'
    setA(fields.a)
    setB(fields.b)
    setModeA(ma)
    setModeB(mb)
    compare(fields.a, fields.b, ma, mb)
  })

  // Marks only when both sides have a breakdown to compare.
  const both = left.phase === 'success' && right.phase === 'success'
  const marks = both ? compareMarks(left.data, right.data) : null
  // What was compared, from each side's own request -- not the inputs now.
  const shareFields = both ? compareShareFields(left.shareFields, right.shareFields) : null

  return (
    <>
      <section className="page-hero" aria-label="Introduction">
        <h1 className="page-hero__title">Compare two names</h1>
        <p className="page-hero__lede">
          Explain two molecules side by side and see which parts of their names differ.
        </p>
      </section>

      <main className="workspace workspace--single compare" aria-label="Compare two names">
        <section className="compare-panel" aria-label="The two molecules">
          <form
            onSubmit={(event) => {
              event.preventDefault()
              if (!busy) compare(a, b)
            }}
            noValidate
          >
            <div className="compare-panel__inputs">
              {/* Nothing here is disabled while busy: a control that disables
                  itself under the keyboard drops focus to <body>. A mode change
                  mid-run is harmless, since compare() reads the modes when it
                  starts and each result keeps the mode it was run in. */}
              <SideInput
                id="compare-a"
                label="A"
                value={a}
                onValue={(v) => { setA(v); setEmpty((e) => e && { ...e, a: false }) }}
                mode={modeA}
                onMode={setModeA}
                invalid={empty?.a}
                noteId="compare-note"
                inputRef={refA}
              />
              <SideInput
                id="compare-b"
                label="B"
                value={b}
                onValue={(v) => { setB(v); setEmpty((e) => e && { ...e, b: false }) }}
                mode={modeB}
                onMode={setModeB}
                invalid={empty?.b}
                noteId="compare-note"
                inputRef={refB}
              />
            </div>
            <div className="compare-panel__actions">
              <button type="submit" className="btn btn--accent" aria-disabled={busy}>
                <Icon name="translate" />
                {busy ? 'Comparing…' : 'Compare'}
              </button>
              {shareFields && <ShareButton fields={shareFields} />}
              {/* .sr-only while empty, so it adds no gap to the row. */}
              <p id="compare-note" className={note ? 'panel-note' : 'sr-only'} role="status">
                {note}
              </p>
            </div>
            <div className="examples" role="group" aria-label="Try a curated example">
              <span className="examples__label">Try one:</span>
              <ul className="examples__list" role="list">
                {EXAMPLES.map((example) => (
                  <li key={example.label}>
                    <button
                      type="button"
                      className="chip"
                      aria-disabled={busy}
                      onClick={() => {
                        if (busy) return
                        setEmpty(null)
                        setA(example.a)
                        setB(example.b)
                        setModeA('name')
                        setModeB('name')
                        compare(example.a, example.b, 'name', 'name')
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

        {both && !marks && (
          <p className="compare-legend workspace__bare">
            One side has no breakdown of its name, so no parts are marked.
          </p>
        )}
        {marks && (
          <p className="compare-legend workspace__bare">
            <span className="explain-name__part--differs">Grey</span> marks a part the other name
            does not have.
          </p>
        )}

        <div className="compare-results workspace__bare">
          <SideResult label="A" explain={left} marks={marks?.a ?? null} />
          <SideResult label="B" explain={right} marks={marks?.b ?? null} />
        </div>
      </main>
    </>
  )
}

export default Compare
