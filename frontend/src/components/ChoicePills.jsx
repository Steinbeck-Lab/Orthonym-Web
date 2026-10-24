/**
 * A small set of mutually exclusive choices as one pill row (/check's "One
 * pair / Upload CSV", /compare's "Name / SMILES"). Radios, not buttons: arrow
 * keys move between them and the choice is announced. No outer margin; the
 * page places it.
 */
export default function ChoicePills({ name, label, options, value, onChange, disabled }) {
  return (
    <div className="choice-pills" role="radiogroup" aria-label={label}>
      {options.map(([option, text]) => (
        <label key={option} className={`choice-pills__opt${value === option ? ' choice-pills__opt--on' : ''}`}>
          <input
            type="radio"
            name={name}
            value={option}
            checked={value === option}
            onChange={() => onChange(option)}
            disabled={disabled}
          />
          {text}
        </label>
      ))}
    </div>
  )
}
