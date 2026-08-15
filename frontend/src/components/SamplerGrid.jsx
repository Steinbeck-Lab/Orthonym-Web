import Tile from './Tile'

const DEFAULT_EMPTY_MESSAGE =
  'Your sampler is bare cloth. Submit a SMILES string above and each row will be sewn in below.'

export default function SamplerGrid({ rows, reduceMotion, emptyMessage = DEFAULT_EMPTY_MESSAGE }) {
  if (!rows.length) {
    return (
      <div className="sampler sampler--empty">
        <p className="sampler__empty-note">{emptyMessage}</p>
      </div>
    )
  }

  return (
    <ul className="sampler" aria-live="polite">
      {rows.map((row, index) => (
        <Tile
          key={`${row.smiles}-${index}`}
          row={row}
          phase={row.phase}
          reduceMotion={reduceMotion}
        />
      ))}
    </ul>
  )
}
