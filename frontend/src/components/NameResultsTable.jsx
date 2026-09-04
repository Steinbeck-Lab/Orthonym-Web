import CopyButton from './CopyButton'
import Icon from './Icon'
import { downloadText, rowsToCsv, rowsToSdf } from '../lib/molExport'

/**
 * The shared "code plus copy button, else a dash" unit behind the SMILES
 * cell, the InChIKey cell and the InChI meta-row -- three near-identical
 * renderings collapsed into one. `fallback` is a node, not always the plain
 * em dash: the SMILES cell's fallback is the row's error message.
 *
 * `className` defaults to the two table cells' wrapper class; the InChI
 * meta-row passes `idlist__value` instead so its rendered class names --
 * and the CSS that targets them -- stay exactly as they were. This is a
 * refactor, not a redesign.
 */
function IdValue({ value, label, title, fallback = '—', className = 'name-results__value' }) {
  if (!value) return <span className="results-cell__none">{fallback}</span>
  return (
    <span className={className}>
      <code title={title}>{value}</code>
      <CopyButton text={value} label={`Copy ${label}`} />
    </span>
  )
}

/**
 * The two-or-more-names view for /from-name.
 *
 * It borrows the `.results-table` SKIN from the naming side but none of its
 * VOCABULARY: no tier modifier, no confidence rule, no round-trip column. This
 * page computes no verdict, and dressing "OPSIN parsed it" in Home's
 * confidence grammar would claim a check that never ran. `.results-group` is
 * used bare, which resolves --tier-accent to --muted: neutral separators and a
 * neutral hover.
 *
 * One <tbody> PER MOLECULE, not one for the whole table: every separator and
 * the hover hang off `.results-group`, so a single tbody would draw one
 * hairline under the entire block and tint every row on hover together.
 *
 * Columns run in the direction of the work: what you typed, what it drew, what
 * it is.
 */
export default function NameResultsTable({ rows }) {
  // Counts only -- cheap to derive on every render. The actual SDF text is
  // built inside the Download button's onClick below; building it here too
  // (rowsToSdf(rows)) would re-run for every re-render of the page that
  // holds this table, including keystrokes elsewhere on the page, just to
  // read two numbers off it.
  const written = rows.filter((r) => r.data?.molblock).length
  const skipped = rows.length - written
  const parsed = rows.filter((r) => r.ok).length

  return (
    <div className="name-results">
      <div className="name-results__bar">
        <span className="name-results__count">
          {parsed} of {rows.length} parsed
        </span>
        <div className="name-results__actions">
          <button
            type="button"
            className="btn btn--pastel btn--sm"
            onClick={() => downloadText('orthonym-from-name.csv', rowsToCsv(rows), 'text/csv')}
          >
            <Icon name="download" />
            Download CSV
          </button>
          <button
            type="button"
            className="btn btn--pastel btn--sm"
            disabled={written === 0}
            onClick={() => {
              const sdf = rowsToSdf(rows)
              downloadText('orthonym-from-name.sdf', sdf.text, 'chemical/x-mdl-sdfile')
            }}
          >
            <Icon name="download" />
            Download SDF
          </button>
        </div>
      </div>

      {/* Said out loud rather than left to be discovered when the file opens
          short: a row with no molblock cannot be written to an SDF. The CSV
          keeps every row, so the two counts genuinely differ. */}
      {skipped > 0 && (
        <p className="name-results__note">
          The SDF holds {written} of {rows.length} — {skipped} could not be given a
          structure. The CSV holds every row.
        </p>
      )}

      <div className="results-table-wrap">
        <table className="results-table">
          <thead>
            <tr>
              <th scope="col" className="results-th--num">#</th>
              <th scope="col">Name you typed</th>
              <th scope="col">Structure</th>
              <th scope="col">SMILES</th>
              <th scope="col">InChIKey</th>
            </tr>
          </thead>
          {/* One tbody PER MOLECULE -- see the component docstring. */}
          {rows.map((row) => (
            <tbody className="results-group" key={row.index}>
              <tr>
                <td className="results-cell--num">{row.index + 1}</td>
                <td className="name-cell">{row.name}</td>
                <td className="results-cell--pic">
                  {row.data?.depiction_svg ? (
                    <img src={row.data.depiction_svg} alt={`2D structure for "${row.name}"`} />
                  ) : (
                    <span className="results-cell__none">—</span>
                  )}
                </td>
                <td className="results-cell--smiles">
                  {/* The failure sits in the widest cell so the message is
                      readable, and the row keeps its number so it still
                      matches the line the user pasted. */}
                  <IdValue
                    value={row.ok ? row.data.smiles : null}
                    label="SMILES"
                    title={row.data?.smiles}
                    fallback={row.error}
                  />
                </td>
                <td className="results-cell--smiles results-cell--key">
                  <IdValue value={row.data?.inchikey} label="InChIKey" />
                </td>
              </tr>
              {/* The second, compact line: the InChI, the one identifier the
                  backend returns that the top row has no room for (canonical
                  SMILES stays off this table -- owner instruction 2026-09-04
                  -- it's still on the single-result card and in the CSV).
                  Only for a row that parsed AND has an InChI -- a failure has
                  no identifiers, and RDKit's InChI writer is not total, so an
                  empty labelled line would be noise. THREE spacer cells (for
                  `#`, Name and Structure -- owner correction, same day: the
                  InChI sits under SMILES and InChIKey, not Structure) push
                  the content to start under the SMILES column, matching
                  ResultsTable.jsx's confidence row; the cell then spans the
                  remaining two columns so the InChI, one unbroken 60+
                  character token, has room to wrap instead of forcing the
                  page sideways. That's less room than a Structure-aligned
                  start would give it, so a long InChI (caffeine's,
                  aspirin's) wraps onto more lines here -- expected, not a
                  bug. */}
              {row.ok && row.data.inchi && (
                <tr className="name-results__meta-row">
                  <td className="name-results__meta-spacer" aria-hidden="true" />
                  <td className="name-results__meta-spacer" aria-hidden="true" />
                  <td className="name-results__meta-spacer" aria-hidden="true" />
                  <td className="name-results__meta-cell" colSpan={2}>
                    <span className="name-results__meta-item">
                      <span className="idlist__label">InChI</span>
                      <IdValue value={row.data.inchi} label="InChI" className="idlist__value" />
                    </span>
                  </td>
                </tr>
              )}
            </tbody>
          ))}
        </table>
      </div>
    </div>
  )
}
