// /compare's marks: which parts of one name the other does not have.
//
// A diff on the explain `nodes` (kind + label), not on the strings: a string
// diff of "propan-1-ol" and "propan-2-ol" would mark a character, while this
// marks the locant part, the thing a reader points at. Counted as a multiset,
// so "2,2-dimethyl" against "2-methyl" marks exactly one "2" and the "di".

const key = (node) => `${node.kind}\u0000${node.label}`

// Placed nodes in the order they are written, then the unplaced ones.
function inOrder(nodes) {
  const start = (node) => (node.span ? node.span[0] : Infinity)
  return [...nodes].sort((x, y) => start(x) - start(y))
}

function unmatched(mine, theirs) {
  const left = new Map()
  for (const node of theirs) left.set(key(node), (left.get(key(node)) ?? 0) + 1)
  const out = new Set()
  for (const node of inOrder(mine)) {
    const n = left.get(key(node)) ?? 0
    if (n > 0) left.set(key(node), n - 1)
    else out.add(node.id)
  }
  return out
}

/** The ids in each list with no partner in the other: `{ a, b }`. */
export function diffNodes(nodesA, nodesB) {
  return { a: unmatched(nodesA, nodesB), b: unmatched(nodesB, nodesA) }
}

/** The marks for two answers, or null when either has no breakdown: an empty
 *  side would mark every part of the other, and the legend would then claim
 *  the other name lacks them all. */
export function compareMarks(dataA, dataB) {
  if (!dataA?.nodes?.length || !dataB?.nodes?.length) return null
  return diffNodes(dataA.nodes, dataB.nodes)
}

/** Share fields for what was COMPARED (each side's request, as useExplain
 *  recorded it), never the inputs as they are now. */
export function compareShareFields(left, right) {
  if (!left || !right) return null
  const side = (f) => (f.name ? [f.name, 'name'] : [f.smiles, 'smiles'])
  const [a, am] = side(left)
  const [b, bm] = side(right)
  return { a, am, b, bm }
}
