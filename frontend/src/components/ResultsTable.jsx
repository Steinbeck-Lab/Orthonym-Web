import { NAMED_STATUSES, STATE_CLASS, STATE_LABEL } from '../lib/statuses'
import useDepiction from '../lib/useDepiction'
import CopyButton from './CopyButton'
import ChemName from './Typeset'
import TierLamp from './TierLamp'

/**
 * The 3-or-more-molecules view: a table with the input and retranslated
 * structures drawn inline. Columns, left to right: number, SMILES, input
 * structure, IUPAC name, retranslated structure. The confidence verdict sits on
 * its own row directly beneath the name and the retranslated structure, tinted
 * by tier (owner instruction 2026-09-03). Cards (SamplerGrid) are the 1-2 view;
 * a 10,000-row job is BatchResults, which draws nothing inline by design.
 */
export default function ResultsTable({ rows }) {
  return (
    <div className="results-table-wrap">
      <table className="results-table">
        <thead>
          <tr>
            <th scope="col" className="results-th--num">#</th>
            <th scope="col">SMILES</th>
            <th scope="col">Input</th>
            <th scope="col">IUPAC name</th>
            <th scope="col">Re-parsed</th>
          </tr>
        </thead>
        {rows.map((row, index) => (
          <ResultRow key={`${row.smiles}-${index}`} row={row} index={index} />
        ))}
      </table>
    </div>
  )
}

function ResultRow({ row, index }) {
  const { smiles, status, name, error, depiction_svg, roundtrip_smiles, roundtrip_match } = row
  const retrans = useDepiction(roundtrip_smiles)
  const named = NAMED_STATUSES.has(status)
  const stateClass = STATE_CLASS[status] || status

  return (
    <tbody className={`results-group results-group--${stateClass}`}>
      <tr className="results-row">
        <td className="results-cell--num">{index + 1}</td>
        <td className="results-cell--smiles">
          <code title={smiles}>{smiles}</code>
        </td>
        <td className="results-cell--pic">
          {depiction_svg ? (
            <img src={depiction_svg} alt={`Structure you entered, "${smiles}"`} />
          ) : (
            <span className="results-cell__none">—</span>
          )}
        </td>
        <td className="results-cell--name">
          {named ? (
            <span className="results-name">
              <span className="results-name__text">
                <ChemName name={name} />
              </span>
              <CopyButton text={name} />
            </span>
          ) : (
            <span className="results-cell__none">
              {status === 'error' ? error || 'Could not parse this SMILES string' : STATE_LABEL[status]}
            </span>
          )}
        </td>
        <td className="results-cell--pic">
          {roundtrip_smiles ? (
            retrans.svg ? (
              <img src={retrans.svg} alt={`Structure OPSIN re-parsed, "${roundtrip_smiles}"`} />
            ) : (
              <span className="results-cell__none">{retrans.loading ? 'Drawing…' : '—'}</span>
            )
          ) : (
            <span className="results-cell__none">—</span>
          )}
        </td>
      </tr>
      {/* The confidence verdict, tinted by tier, directly beneath the name and
          the retranslated structure -- the two columns it speaks about. */}
      <tr className="results-conf-row">
        <td className="results-conf-row__spacer" aria-hidden="true" />
        <td className="results-conf-row__spacer" aria-hidden="true" />
        <td className="results-conf-row__spacer" aria-hidden="true" />
        <td className="results-conf-cell" colSpan={2}>
          <span className="results-conf">
            <TierLamp status={status} />
            <span className="results-conf__tier">{STATE_LABEL[status] || 'Error'}</span>
            {named && roundtrip_smiles && (
              <span className="results-conf__rt">
                {roundtrip_match ? 'round-trip ✓' : 'round-trip ✗'}
              </span>
            )}
          </span>
        </td>
      </tr>
    </tbody>
  )
}
