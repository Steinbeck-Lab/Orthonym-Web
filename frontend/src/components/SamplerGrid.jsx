import Tile from './Tile'

const DEFAULT_EMPTY_MESSAGE =
  'The register is empty. Submit a SMILES string above and each entry will be listed below.'

export default function SamplerGrid({ rows, reduceMotion, emptyMessage = DEFAULT_EMPTY_MESSAGE }) {
  if (!rows.length) {
    return (
      <div className="sampler sampler--empty">
        <p className="sampler__empty-note">{emptyMessage}</p>
      </div>
    )
  }

  return (
    /* Not a live region: a tile resolving character by character would be
       read out piece by piece. The page announces a one-line summary. */
    <ul className="sampler">
      {rows.map((row, index) => (
        <Tile
          key={`${row.smiles}-${index}`}
          row={row}
          phase={row.phase}
          index={index}
          reduceMotion={reduceMotion}
        />
      ))}
    </ul>
  )
}
