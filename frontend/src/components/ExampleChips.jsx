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
        {examples.map((example) => (
          <li key={example.smiles}>
            <button
              type="button"
              className="chip"
              disabled={disabled}
              onClick={() => onPick(example)}
              title={example.smiles}
            >
              {example.label}
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}
