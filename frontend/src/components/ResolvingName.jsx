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
//
// The visually-hidden copy is the RAW name -- caret and all -- not the
// typeset one. It is the string the copy button puts on the clipboard and
// the string OPSIN reads back, so what a screen reader hears and what a
// sighted reader can copy stay the same text.

import { nameRuns, applyRuns } from '../lib/nameTypography'

const TAG = { italic: 'i', super: 'sup', sub: 'sub' }

export default function ResolvingName({ name, animate }) {
  // IUPAC typography first, character cells inside it: the italic run of a
  // stereodescriptor has to wrap whole cells, and a cell cannot be half
  // italic. The cell index keeps counting ACROSS pieces so the reveal still
  // staggers left to right over the whole name rather than restarting at
  // every descriptor.
  const pieces = applyRuns(name, nameRuns(name))
  let cellIndex = 0

  return (
    <span className={`citation-name${animate ? ' citation-name--animate' : ''}`}>
      <span className="sr-only">{name}</span>
      <span className="citation-name__visual" aria-hidden="true">
        {pieces.map((piece, pieceIndex) => {
          // The superscript caret is notation, not a printed character.
          if (piece.style === 'hidden') return null

          const cells = Array.from(piece.text).flatMap((char, index) => {
            const cell = (
              <span
                className="citation-name__cell"
                key={`c${pieceIndex}-${index}`}
                style={{ '--cell-index': cellIndex }}
              >
                {char === ' ' ? ' ' : char}
              </span>
            )
            cellIndex += 1
            // A long IUPAC name must break only at chemical boundaries, never
            // mid-token: the per-character spans would otherwise let a line
            // break land inside a word (e.g. "propanoic"). A <wbr> after a
            // closing bracket, brace, or comma gives the wrapper a legal break
            // opportunity there; hyphens already provide their own. With these
            // in place, `overflow-wrap: normal` never has to break a token.
            if (char === ')' || char === ']' || char === '}' || char === ',') {
              return [cell, <wbr key={`w${pieceIndex}-${index}`} />]
            }
            return [cell]
          })

          const Tag = TAG[piece.style]
          if (!Tag) return cells
          return (
            <Tag className="chem-mark" key={`p${pieceIndex}`}>
              {cells}
            </Tag>
          )
        })}
      </span>
    </span>
  )
}
