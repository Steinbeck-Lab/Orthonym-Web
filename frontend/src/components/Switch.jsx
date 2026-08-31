/**
 * A machined two-position switch.
 *
 * Built as a real <button role="switch"> rather than a styled checkbox so
 * the accessible name, the pressed state and keyboard operation all come
 * from the platform. Space and Enter both toggle it for free.
 *
 * The state is never carried by knob position alone: the track inverts
 * (transparent-with-outline -> filled ink, the same "engaged = fill"
 * language the primary button uses on hover) AND a mono state word sits
 * beside it. In a system with no accent colour and no shadow, position
 * plus fill plus a word is the whole vocabulary available, and a switch
 * that relied on position alone would be unreadable to anyone who cannot
 * compare it against a second switch in the other state.
 */
export default function Switch({ id, checked, onChange, disabled, label, hint, onWord, offWord }) {
  const hintId = hint ? `${id}-hint` : undefined

  return (
    <div className="switch-field">
      <button
        type="button"
        id={id}
        role="switch"
        aria-checked={checked}
        aria-describedby={hintId}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={`switch${checked ? ' switch--on' : ''}`}
      >
        <span className="switch__track" aria-hidden="true">
          <span className="switch__knob" />
        </span>
        <span className="switch__label">{label}</span>
        <span className="switch__state">{checked ? onWord : offWord}</span>
      </button>
      {hint && (
        <p className="switch__hint" id={hintId}>
          {hint}
        </p>
      )}
    </div>
  )
}
