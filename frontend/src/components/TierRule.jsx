import { STATE_CLASS } from '../lib/statuses'

/**
 * The rule under a name, drawn rather than bordered: double for a PIN, dashed
 * for a fallback, dotted for a best effort, one faint line for no name. A
 * 1px CSS `dotted` border renders as a continuous hairline at normal zoom,
 * which collapses best effort into no name -- two tiers told apart by grey
 * value only. As SVG strokes the dots are real dots, so the ladder stays a
 * ladder of FORM. `vector-effect: non-scaling-stroke` keeps the stroke weight
 * exact while the line stretches to its measure.
 */
export default function TierRule({ status, className = '' }) {
  const tier = STATE_CLASS[status]
  if (!tier || tier === 'error') return null
  return (
    <svg
      className={`tier-rule tier-rule--${tier} ${className}`.trim()}
      viewBox="0 0 100 6"
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      {tier === 'pin' ? (
        <>
          <line x1="0" y1="1" x2="100" y2="1" />
          <line x1="0" y1="5" x2="100" y2="5" />
        </>
      ) : (
        <line x1="0" y1="3" x2="100" y2="3" />
      )}
    </svg>
  )
}
