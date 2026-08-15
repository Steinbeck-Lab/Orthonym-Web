// Renders a chemical name as individually-stitched characters.
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
// individually-stitched character cells.
export default function StitchedName({ name, animate }) {
  const characters = Array.from(name)

  return (
    <span className={`stitched-name${animate ? ' stitched-name--animate' : ''}`}>
      <span className="sr-only">{name}</span>
      <span className="stitched-name__visual" aria-hidden="true">
        {characters.map((char, index) => (
          <span className="stitched-name__cell" key={index} style={{ '--cell-index': index }}>
            {char === ' ' ? ' ' : char}
          </span>
        ))}
      </span>
    </span>
  )
}
