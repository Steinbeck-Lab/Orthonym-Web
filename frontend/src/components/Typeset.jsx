// Sets a chemical name, or a molecular formula, the way IUPAC prints it.
//
// The rules live in lib/nameTypography.js; this file is only the markup for
// them. It is deliberately thin, because there is no single place a name is
// rendered in Orthonym -- there are seven, across four pages, in two typefaces
// -- and each of them needs the same typography inside its own wrapper.
//
// ELEMENT CHOICE. <i> and not <em>: this is the technical-convention italic
// (a locant, a descriptor, a fusion letter), not emphasis, and <em> would have
// a screen reader stress the letter. <sup>/<sub> are the real elements rather
// than a CSS class, so a raised locant survives being copied out of the DOM
// into anything that understands HTML.
//
// The hidden caret: nameTypography marks the "^" of a von Baeyer superscript
// as `hidden`, and it is dropped from the DOM here. IUPAC prints no caret --
// the digits are simply raised. The exact engine string, caret included, is
// still what the copy button, the CSV and the SDF write, because all three
// read the data object and never the page.

import { nameRuns, formulaRuns, applyRuns } from '../lib/nameTypography'

const TAG = { italic: 'i', super: 'sup', sub: 'sub' }

/**
 * Renders `{ text, style }` pieces.
 *
 * Exported for the callers that do their own cutting first: /explain slices
 * the name by the backend's `name_range` offsets into hover targets, then asks
 * nameTypography for the runs inside each target's range and hands them here.
 */
export function Pieces({ pieces }) {
  return (
    <>
      {pieces.map((piece, index) => {
        if (piece.style === 'hidden') return null
        const Tag = TAG[piece.style]
        if (!Tag) return piece.text
        return (
          <Tag key={index} className="chem-mark">
            {piece.text}
          </Tag>
        )
      })}
    </>
  )
}

/** A whole IUPAC name, typeset. */
export default function ChemName({ name }) {
  if (!name) return null
  return <Pieces pieces={applyRuns(name, nameRuns(name))} />
}

/** A molecular formula, with its counts subscript and any charge raised. */
export function ChemFormula({ formula }) {
  if (!formula) return null
  return <Pieces pieces={applyRuns(formula, formulaRuns(formula))} />
}
