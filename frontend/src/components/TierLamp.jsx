import { STATE_CLASS } from '../lib/statuses'

/**
 * The confidence lamp: a small lit indicator beside the tier label, wherever a
 * name and its tier appear.
 *
 * WHY IT IS A SHAPE AND NOT JUST A COLOUR
 *
 * The ask was "PIN means green, no name means red, other colours in between".
 * Built as hue alone, that ramp does not work: measured across the five
 * tokens, adjacent lit steps separate by only 1.03-1.11:1 under deuteranopia,
 * and the best pair anywhere in the ramp reaches 1.17:1. For roughly 8% of
 * male readers a pure hue ramp is decoration, not information -- and a
 * confidence signal that some readers cannot rank is exactly the overstatement
 * Product Principle 2 forbids.
 *
 * So the LADDER is carried by form, and the form is not invented: each lamp
 * wears its own tier's rule pattern, the grammar this app already uses under
 * every name. Double ring = verified PIN. Dashed = verified fallback. Dotted =
 * best effort. Plain thin ring, unlit = the engine declined. Struck ring = no
 * name could be produced (bad input, or naming failed). Read in greyscale, at
 * 1px, or by a reader with any
 * of the three common colour deficiencies, the five are still five.
 *
 * Hue then rides along as reinforcement, never as the signal: green for the
 * verified pair, amber for best effort, grey for a declined name, red for an
 * error. PIN and FALLBACK deliberately share the green FAMILY, because they
 * genuinely share the claim -- both are the verified tiers -- and the
 * ring pattern is what tells them apart. Colour separating them would be a
 * distinction hue cannot reliably carry anyway.
 *
 * The lamp NEVER replaces anything. The rule under the name and the plain-text
 * tier label both stay exactly as they were, so nothing here is colour-only
 * (WCAG 1.4.1) and the lamp is `aria-hidden` -- the label beside it already
 * says the tier, and announcing it twice is noise.
 *
 * The crimson chrome accent is not in this palette. `--tier-stop` is a
 * separate, darker red, because the accent belongs to the site chrome and must
 * never read as a result.
 */

// The five forms. Each is that tier's own rule, bent into a ring.
//
// Drawn on an 18-unit grid at 18px, so one unit is one pixel and the stroke
// widths are the real ones. non-scaling-stroke is deliberately NOT used: the
// lamp is never scaled, and the property would defeat the dasharrays if it
// ever were (measured on the legend's specimens, whose dashes vanish under a
// non-uniform stretch).
function LampMark({ tier }) {
  const ring = { fill: 'none', stroke: 'currentColor', strokeLinecap: 'butt' }
  return (
    <svg
      className="tier-lamp__mark"
      viewBox="0 0 18 18"
      width="18"
      height="18"
      aria-hidden="true"
    >
      {tier === 'pin' && (
        <>
          {/* Two concentric rings, 2.5 units apart: the double rule, closed. */}
          <circle {...ring} cx="9" cy="9" r="8" strokeWidth="1.25" />
          <circle {...ring} cx="9" cy="9" r="5.5" strokeWidth="1.25" />
          <circle cx="9" cy="9" r="3" fill="currentColor" />
        </>
      )}
      {tier === 'fallback' && (
        <>
          {/* 10:7 dash-to-gap, the ratio the legend's dashed specimen uses,
              scaled to this circumference (2*pi*7 = 43.98 -> 8 dashes). */}
          <circle
            {...ring}
            cx="9"
            cy="9"
            r="7"
            strokeWidth="1.75"
            strokeDasharray="3.23 2.27"
          />
          <circle cx="9" cy="9" r="3" fill="currentColor" />
        </>
      )}
      {tier === 'best_effort' && (
        /* Dotted, and HOLLOW: the one named tier that is not a verified
           tier gets no core. 2:6 dash ratio, again from the legend's own
           specimen. */
        <circle
          {...ring}
          cx="9"
          cy="9"
          r="7"
          strokeWidth="1.75"
          strokeDasharray="1.1 3.3"
        />
      )}
      {tier === 'abstain' && (
        /* The faint plain rule, closed. Thin, hollow, unlit -- an honest
           abstention is not an alarm, so it gets no fill and no glow. */
        <circle {...ring} cx="9" cy="9" r="7" strokeWidth="1" />
      )}
      {tier === 'error' && (
        <>
          <circle {...ring} cx="9" cy="9" r="7" strokeWidth="1" />
          {/* Struck, like the error rule under a name. A diagonal reads as a
              strike at this size where the legend's vertical ticks would just
              look like a broken ring. */}
          <line {...ring} x1="3.4" y1="14.6" x2="14.6" y2="3.4" strokeWidth="1.25" />
        </>
      )}
    </svg>
  )
}

/**
 * @param status one of the five API statuses. An unknown one renders nothing
 *   rather than guessing a tier -- the same refusal Icon.jsx makes for an
 *   unknown name, and far better than lighting a lamp for a confidence this
 *   component cannot vouch for.
 * @param fresh true on a result that has just arrived, which is the only time
 *   a PIN's lamp breathes.
 */
export default function TierLamp({ status, fresh = false }) {
  const cls = STATE_CLASS[status]
  if (!cls) return null
  return (
    <span
      className={`tier-lamp tier-lamp--${cls}${fresh ? ' tier-lamp--fresh' : ''}`}
      aria-hidden="true"
    >
      {/* The glow is its own element so the mark's edges stay crisp: a filter
          or box-shadow on the mark itself would blur the ring patterns the
          whole design rests on (the measured reason is recorded at
          App.css:3605 for the INFO bulb). */}
      <span className="tier-lamp__glow" />
      <LampMark tier={status} />
    </span>
  )
}
