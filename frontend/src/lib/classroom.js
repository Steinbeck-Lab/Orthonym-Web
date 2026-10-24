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
 *  stems under four letters (locants, "di") are too common to judge. */
export function lineGivesAway(line, hiddenLabels) {
  const text = (line || '').toLowerCase()
  return hiddenLabels.some((label) => {
    const stem = label.toLowerCase().replace(/[^a-z]/g, '').replace(MULTIPLIER, '')
    return stem.length >= 4 && text.includes(stem)
  })
}
