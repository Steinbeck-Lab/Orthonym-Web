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
// as `hidden`. IUPAC prints no caret -- the digits are simply raised -- so it
// takes no space and is not read aloud, but it STAYS in the DOM: a visitor who
// selects the shown name and presses Ctrl+C must get the engine's exact string
// ("0^4,9"), and a removed caret copied as "04,9", a different name. The copy
// button, the CSV and the SDF read the data object, never the page.

import { Fragment } from 'react'
import { nameRuns, formulaRuns, applyRuns, breakSegments } from '../lib/nameTypography'

const TAG = { italic: 'i', super: 'sup', sub: 'sub' }
const HIDDEN_STYLE = { fontSize: 0 }

/**
 * Renders `{ text, style }` pieces.
 *
 * Exported for the callers that do their own cutting first: /explain slices
 * the name by the backend's node spans into hover targets, then asks
 * nameTypography for the runs inside each target's range and hands them here.
 */
export function Pieces({ pieces, breaks = true }) {
  return (
    <>
      {pieces.map((piece, index) => {
        if (piece.style === 'hidden') {
          // font-size 0, not display:none or removal: zero width, but still in
          // the text a selection copies (measured in headless Chromium).
          return (
            <span key={index} aria-hidden="true" style={HIDDEN_STYLE}>
              {piece.text}
            </span>
          )
        }
        const Tag = TAG[piece.style]
        // Plain text gets a <wbr> at each chemical boundary (breakSegments);
        // a styled run stays whole, so a raised locant never splits.
        if (!Tag) {
          if (!breaks) return piece.text
          return (
            <Fragment key={index}>
              {breakSegments(piece.text).map((segment, i) => (
                <Fragment key={i}>
                  {i > 0 && <wbr />}
                  {segment}
                </Fragment>
              ))}
            </Fragment>
          )
        }
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
