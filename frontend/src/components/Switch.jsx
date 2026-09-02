/**
 * A two-position ROCKER, built as a piece of hardware.
 *
 * Ported by shape from a toggle the owner pinned (21st.dev, Ravi Katiyar);
 * none of its code is here. That reference is not an iOS pill -- it is a
 * moulded rocker: a light grey well with an inset rim, a near-black paddle
 * with two grip lines down its middle, and a pair of indicator lamps
 * FLANKING the track, the one on the live side lit.
 *
 * Two intermediate versions were wrong and are worth naming, because both
 * are the obvious thing to reach for again. The first was machined -- a hard
 * 0-radius track with a square knob -- which was right while every button
 * in the system was a flat 0-radius outline, and stopped being right the
 * moment the buttons became round glossy pills. The second was an iOS pill:
 * a circle knob sliding in a crimson glass track, matching the buttons. It
 * matched them so well that it stopped being a switch and started being a
 * small button.
 *
 * The lamps light in CRIMSON on both sides rather than red-for-off and
 * green-for-on. The reference does the latter; here it would mean two new
 * hues in a system with exactly one accent, and it would say that turning
 * best-effort OFF is an error -- when off is the stricter, more conservative
 * setting. The lamp marks which side is live, which is all it has to do.
 *
 * Built as a real <button role="switch"> rather than a styled checkbox, so
 * the accessible name, the state and keyboard operation all come from the
 * platform. Space and Enter both toggle it for free.
 *
 * THE STATE IS CARRIED FOUR WAYS, and colour is never one of them alone
 * (DESIGN.md): the paddle's POSITION, which LAMP is lit, the lamp's own
 * filled-vs-hollow shape, and the mono state word beside it. A switch that
 * relied on position alone is unreadable to anyone who cannot compare it
 * against a second switch in the other state.
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
        {/* The lamps sit OUTSIDE the well, one per side, and the lit one
            says which side is live. Filled-with-a-glow vs a hollow ring, so
            the difference survives without colour. */}
        <span className="switch__lamp switch__lamp--off" aria-hidden="true" />
        <span className="switch__well" aria-hidden="true">
          {/* The paddle. Its grip lines are drawn by CSS, not by an icon:
              they are a moulded texture, not a symbol. */}
          <span className="switch__paddle" />
        </span>
        <span className="switch__lamp switch__lamp--on" aria-hidden="true" />
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
