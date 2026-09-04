import CopyButton from './CopyButton'
import Icon from './Icon'
import { downloadText, rowsToCsv, rowsToSdf } from '../lib/molExport'

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
  const sdf = rowsToSdf(rows)
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
            disabled={sdf.written === 0}
            onClick={() =>
              downloadText('orthonym-from-name.sdf', sdf.text, 'chemical/x-mdl-sdfile')
            }
          >
            <Icon name="download" />
            Download SDF
          </button>
        </div>
      </div>

      {/* Said out loud rather than left to be discovered when the file opens
          short: a row with no molblock cannot be written to an SDF. The CSV
          keeps every row, so the two counts genuinely differ. */}
      {sdf.skipped > 0 && (
        <p className="name-results__note">
          The SDF holds {sdf.written} of {rows.length} — {sdf.skipped} could not be given a
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
                  {row.ok ? (
                    <span className="name-results__value">
                      <code title={row.data.smiles}>{row.data.smiles}</code>
                      <CopyButton text={row.data.smiles} label="Copy SMILES" />
                    </span>
                  ) : (
                    /* The failure sits in the widest cell so the message is
                       readable, and the row keeps its number so it still
                       matches the line the user pasted. */
                    <span className="results-cell__none">{row.error}</span>
                  )}
                </td>
                <td className="results-cell--smiles">
                  {row.data?.inchikey ? (
                    <span className="name-results__value">
                      <code>{row.data.inchikey}</code>
                      <CopyButton text={row.data.inchikey} label="Copy InChIKey" />
                    </span>
                  ) : (
                    <span className="results-cell__none">—</span>
                  )}
                </td>
              </tr>
              {/* The second, compact line: canonical SMILES and InChI, the two
                  identifiers the backend returns that the top row has no room
                  for. Only for a row that parsed AND has at least one of the
                  two -- a failure has no identifiers, and an empty labelled
                  line would be noise (requirement 5). Spans the row past the
                  narrow InChIKey column so the InChI, one unbroken 60+
                  character token, has room to wrap instead of forcing the
                  page sideways. */}
              {row.ok && (row.data.canonical_smiles || row.data.inchi) && (
                <tr className="name-results__meta-row">
                  <td className="name-results__meta-spacer" aria-hidden="true" />
                  <td className="name-results__meta-cell" colSpan={4}>
                    <span className="name-results__meta-item">
                      <span className="idlist__label">Canonical</span>
                      {row.data.canonical_smiles ? (
                        <span className="idlist__value">
                          <code>{row.data.canonical_smiles}</code>
                          <CopyButton
                            text={row.data.canonical_smiles}
                            label="Copy canonical SMILES"
                          />
                        </span>
                      ) : (
                        <span className="results-cell__none">—</span>
                      )}
                    </span>
                    <span className="name-results__meta-item name-results__meta-item--inchi">
                      <span className="idlist__label">InChI</span>
                      {row.data.inchi ? (
                        <span className="idlist__value">
                          <code>{row.data.inchi}</code>
                          <CopyButton text={row.data.inchi} label="Copy InChI" />
                        </span>
                      ) : (
                        <span className="results-cell__none">—</span>
                      )}
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
