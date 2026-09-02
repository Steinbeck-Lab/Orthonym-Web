import Icon from './Icon'

/**
 * A two-position switch, in the same glass the buttons wear.
 *
 * It was a MACHINED switch until 2026-09-02: a hard-edged 0-radius track
 * with a square knob, which was right while every button in the system was
 * a flat 0-radius outline. Once the buttons became deeply round glossy
 * pills, the rectangle was the only control left disagreeing with the rest
 * of the interface -- so the track is now a pill that fills with crimson
 * glass, and the knob is a circle that slides.
 *
 * Built as a real <button role="switch"> rather than a styled checkbox, so
 * the accessible name, the state and keyboard operation all come from the
 * platform. Space and Enter both toggle it for free.
 *
 * THE STATE IS CARRIED THREE WAYS, and that is deliberate: knob POSITION,
 * the track's fill, and a mono state word beside it -- plus a check inside
 * the knob as a fourth. Colour is never the only signal (DESIGN.md), and a
 * switch that relied on position alone is unreadable to anyone who cannot
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
          <span className="switch__knob">
            {/* Inside the knob, so it travels with it. aria-hidden by way of
                Icon -- the state is already announced by aria-checked. */}
            {checked && <Icon name="check" size={12} />}
          </span>
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
