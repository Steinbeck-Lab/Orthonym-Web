// Classroom mode on /explain: the name hidden, revealed one part at a time.

/** Node ids in the order their first piece is written (pieces from
 *  sliceName), each once; then the parts OPSIN gave no place in the name, in
 *  list order, so none is skipped. */
export function revealSteps(pieces, nodes) {
  const steps = []
  for (const piece of pieces) {
    if (piece.nodeId && !steps.includes(piece.nodeId)) steps.push(piece.nodeId)
  }
  for (const node of nodes) {
    if (!node.span && !steps.includes(node.id)) steps.push(node.id)
  }
  return steps
}

/** The ids still hidden at `step` (0 hides all, steps.length hides none). */
export function hiddenAt(steps, step) {
  return new Set(steps.slice(step))
}

const MULTIPLIER = /^(di|tri|tetra|penta|hexa|hepta|octa|nona|deca|bis|tris)/

/** Whether a detail line names a part that is still hidden. A label is
 *  reduced to its stem ("dihydro" -> "hydro", which "hydrogen" contains);
 *  stems under four letters (locants, "di") are too common to judge. The whole
 *  label is checked as well: the multiplier strip also eats the head of the
 *  C5-C10 stems ("hexane" -> "ne"), and those names are themselves the giveaway. */
export function lineGivesAway(line, hiddenLabels) {
  const text = (line || '').toLowerCase()
  return hiddenLabels.some((label) => {
    const whole = label.toLowerCase().replace(/[^a-z]/g, '')
    const stem = whole.replace(MULTIPLIER, '')
    // A bare multiplier ("tetra") is not checked whole: "tetrahedral" would hide it.
    const parts = stem ? [whole, stem] : []
    return parts.some((part) => part.length >= 4 && text.includes(part))
  })
}
