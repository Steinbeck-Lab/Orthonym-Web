// Renders a chemical name as individually-resolving characters.
// When `animate` is true each character gets a staggered CSS animation
// (ink resolving into focus); when false (settled tiles, or
// prefers-reduced-motion) every character is simply present, no motion.
//
// Accessibility note: a bare <span> has the implicit ARIA role "generic",
// and the ARIA spec explicitly prohibits "name from author" for that role
// -- an aria-label on a plain span is dropped by conformant browsers/ATs,
// so the per-character markup can never itself carry the accessible name.
// Instead we render the real name once as visually-hidden text (read
// normally by any AT) alongside an aria-hidden visual rendering built from
// individually-resolving character cells.
export default function StitchedName({ name, animate }) {
  const characters = Array.from(name)

  return (
    <span className={`citation-name${animate ? ' citation-name--animate' : ''}`}>
      <span className="sr-only">{name}</span>
      <span className="citation-name__visual" aria-hidden="true">
        {characters.flatMap((char, index) => {
          const cell = (
            <span className="citation-name__cell" key={`c${index}`} style={{ '--cell-index': index }}>
              {char === ' ' ? ' ' : char}
            </span>
          )
          // A long IUPAC name must break only at chemical boundaries, never
          // mid-token: the per-character spans would otherwise let a line
          // break land inside a word (e.g. "propanoic"). A <wbr> after a
          // closing bracket, brace, or comma gives the wrapper a legal break
          // opportunity there; hyphens already provide their own. With these
          // in place, `overflow-wrap: normal` never has to break a token.
          if (char === ')' || char === ']' || char === '}' || char === ',') {
            return [cell, <wbr key={`w${index}`} />]
          }
          return [cell]
        })}
      </span>
    </span>
  )
}
