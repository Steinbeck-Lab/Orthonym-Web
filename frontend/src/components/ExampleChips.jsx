export default function ExampleChips({ examples, error, disabled, onPick }) {
  if (error) {
    return (
      <p className="examples__error" role="status">
        Curated examples didn&rsquo;t load ({error}). You can still type a SMILES string above.
      </p>
    )
  }

  if (!examples.length) {
    return (
      <p className="examples__loading" aria-hidden="true">
        Loading curated examples&hellip;
      </p>
    )
  }

  return (
    <div className="examples" role="group" aria-label="Try a curated example">
      <span className="examples__label">Try one:</span>
      <ul className="examples__list">
        {examples.map((example, i) => (
          <li key={example.smiles} style={{ '--i': i }}>
            {/* The molecule, not the lesson. The API labels read "Ethanol --
                a confirmed PIN", which stacked four chips into 87px of a
                page that has to fit one screen; the tier each one
                demonstrates is what the key band at the foot explains, and
                the full label is still the accessible name and the tooltip.
                Split on the em dash the backend uses, and fall back to the
                whole label if it ever stops using one. */}
            <button
              type="button"
              className="chip"
              disabled={disabled}
              onClick={() => onPick(example)}
              title={`${example.label} — ${example.smiles}`}
              aria-label={example.label}
            >
              {example.label.split('—')[0].trim() || example.label}
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}
