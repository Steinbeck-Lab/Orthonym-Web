/**
 * The × that joins two names — drawn as two strokes, not typed as a letter.
 *
 * Two strokes crossing is what "×" means between collaborators, which is why
 * this mark is drawn rather than being a multiplication sign borrowed from the
 * character set. It
 * is also why it must never be replaced with a literal "x": an icon made of
 * type is the thing the craft rules bar, and here the drawn version carries
 * meaning the glyph does not.
 *
 * ONE CONSUMER TODAY, and the honest history is worth keeping: this was pulled
 * out of Footer when the About page's collaboration block looked like it wanted
 * the same join, and then About took a painted mark (BrushCross) instead --
 * because at signature scale a hairline cross reads as nothing. So the
 * extraction outlived its second consumer. It stays a component rather than
 * folding back into Footer for one reason only: the geometry note below is the
 * kind of thing that gets silently broken by a well-meaning edit, and it is
 * easier to protect in a file that does one thing.
 *
 * The dasharray of 13 in CSS is not arbitrary: each stroke is 9-9-root-2 =
 * 12.73 units long, so one dash covers a whole path exactly once and the
 * stroke can be drawn on as though it were being sewn. Callers pass their own
 * class so each surface owns its size and its animation trigger; the geometry
 * is the only thing shared.
 */
export default function CreditCross({ className = 'credit__x', strokeClassName = 'credit__x-stroke' }) {
  return (
    <svg
      className={className}
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      aria-hidden="true"
      focusable="false"
    >
      <path className={strokeClassName} d="M3.5 3.5 12.5 12.5" />
      <path className={strokeClassName} d="M12.5 3.5 3.5 12.5" />
    </svg>
  )
}
