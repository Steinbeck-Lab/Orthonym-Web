import { useState } from 'react'
import ExplainView from '../components/ExplainView'
import Icon from '../components/Icon'
import ReportLink from '../components/ReportLink'
import ShareButton from '../components/ShareButton'
import TransportNotice from '../components/TransportNotice'
import { compareMarks, compareShareFields } from '../lib/compareNodes'
import useExplain, { TIER_SETTINGS } from '../lib/useExplain'
import useShareLink from '../lib/useShareLink'
// Explain.css styles ExplainView; Check.css holds the two-choice switch.
import './Explain.css'
import './Check.css'
import './Compare.css'

const EXAMPLES = [
  { label: 'propan-1-ol vs propan-2-ol', a: 'propan-1-ol', b: 'propan-2-ol' },
  { label: '2-methyl vs 2,2-dimethylbutane', a: '2-methylbutane', b: '2,2-dimethylbutane' },
]

// One side's input: a name or a SMILES, its own toggle.
function SideInput({ id, label, value, onValue, mode, onMode, disabled }) {
  return (
    <div className="compare-input">
      <div className="compare-input__head">
        <span className="compare-input__label">{label}</span>
        <div className="check-mode" role="radiogroup" aria-label={`${label}: name or SMILES`}>
          {[
            ['name', 'Name'],
            ['smiles', 'SMILES'],
          ].map(([v, text]) => (
            <label key={v} className={`check-mode__opt${mode === v ? ' check-mode__opt--on' : ''}`}>
              <input
                type="radio"
                name={`${id}-mode`}
                value={v}
                checked={mode === v}
                onChange={() => onMode(v)}
                disabled={disabled}
              />
              {text}
            </label>
          ))}
        </div>
      </div>
      <div className="field field--framed">
        <label htmlFor={id} className="field__label">
          {mode === 'name' ? 'IUPAC name' : 'Structure (SMILES)'}
        </label>
        <input
          id={id}
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
  const { phase, data, apiError, fetchError, tierRow, resultMode } = explain
  return (
    <section className="compare-side" aria-label={`${label}: explanation`} aria-busy={phase === 'loading'}>
      <h2 className="compare-side__label">{label}</h2>
      {fetchError && (
        <p className="notice" role="alert">
          <TransportNotice error={fetchError} />
        </p>
      )}
      {phase === 'idle' && !fetchError && <p className="compare-side__empty">Nothing here yet.</p>}
      {phase === 'loading' && <p className="compare-side__empty">Naming and decomposing…</p>}
      {phase === 'error' && (
        <div role="alert">
          <p className="compare-side__empty">{apiError || 'Could not explain this molecule'}</p>
          <ReportLink row={tierRow} where="Compare" settings={TIER_SETTINGS} />
        </div>
      )}
      {phase === 'success' && (
        <ExplainView
          key={`${resultMode}:${data?.smiles}:${data?.name}`}
          data={data}
          resultMode={resultMode}
          tierRow={tierRow}
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
  const left = useExplain()
  const right = useExplain()
  const busy = left.phase === 'loading' || right.phase === 'loading'

  function compare(va, vb, ma = modeA, mb = modeB) {
    const x = va.trim()
    const y = vb.trim()
    if (!x || !y) {
      setNote('Enter something on both sides.')
      return
    }
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

      <main className="workspace compare" aria-label="Compare two names">
        <section className="compare-panel" aria-label="The two molecules">
          <form
            onSubmit={(event) => {
              event.preventDefault()
              compare(a, b)
            }}
            noValidate
          >
            <div className="compare-panel__inputs">
              <SideInput id="compare-a" label="A" value={a} onValue={setA} mode={modeA} onMode={setModeA} disabled={busy} />
              <SideInput id="compare-b" label="B" value={b} onValue={setB} mode={modeB} onMode={setModeB} disabled={busy} />
            </div>
            <div className="compare-panel__actions">
              <button type="submit" className="btn btn--accent" disabled={busy}>
                <Icon name="translate" />
                {busy ? 'Comparing…' : 'Compare'}
              </button>
              {shareFields && <ShareButton fields={shareFields} />}
              {note && (
                <p className="compare-panel__note" role="status">
                  {note}
                </p>
              )}
            </div>
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
          <p className="compare-legend">
            One side has no breakdown of its name, so no parts are marked.
          </p>
        )}
        {marks && (
          <p className="compare-legend">
            <span className="explain-name__part--differs">Grey</span> marks a part the other name
            does not have.
          </p>
        )}

        <div className="compare-results">
          <SideResult label="A" explain={left} marks={marks?.a ?? null} />
          <SideResult label="B" explain={right} marks={marks?.b ?? null} />
        </div>
      </main>
    </>
  )
}

export default Compare
