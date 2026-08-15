// Renders a chemical name as individually-sewn characters.
// When `animate` is true each character gets a staggered CSS animation
// (the "embroidery" reveal); when false (settled tiles, or
// prefers-reduced-motion) every character is simply present, no motion.
//
// Accessibility note: a bare <span> has the implicit ARIA role "generic",
// and the ARIA spec explicitly prohibits "name from author" for that role
// -- an aria-label on a plain span is dropped by conformant browsers/ATs,
// so the per-character markup can never itself carry the accessible name.
// Instead we render the real name once as visually-hidden text (read
// normally by any AT) alongside an aria-hidden visual rendering built from
// individually-sewn character cells.
export default function ThreadedName({ name, animate }) {
  const characters = Array.from(name)

  return (
    <span className={`threaded-name${animate ? ' threaded-name--animate' : ''}`}>
      <span className="sr-only">{name}</span>
      <span className="threaded-name__visual" aria-hidden="true">
        {characters.map((char, index) => (
          <span className="threaded-name__cell" key={index} style={{ '--cell-index': index }}>
            {char === ' ' ? ' ' : char}
          </span>
        ))}
      </span>
    </span>
  )
}
