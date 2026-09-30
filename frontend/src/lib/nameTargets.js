// frontend/src/lib/nameTargets.js
// Explain v2: the response is a flat list of nodes with `parent` links.
// Each character of the name belongs to the SMALLEST node whose span covers
// it, so a locant inside a part wins the hover over the part around it.

const PART_KINDS = new Set(['substituent', 'parent', 'suffix'])

export function nodeById(nodes, id) {
  if (id === null || id === undefined || !nodes) return null
  return nodes.find((node) => node.id === id) || null
}

export function isPart(node) {
  return Boolean(node) && PART_KINDS.has(node.kind)
}

// The part a node belongs to: itself when it is one, else its nearest part ancestor.
export function partOf(nodes, id) {
  let node = nodeById(nodes, id)
  const seen = new Set()
  while (node && !isPart(node) && !seen.has(node.id)) {
    seen.add(node.id)
    node = nodeById(nodes, node.parent)
  }
  return isPart(node) ? node : null
}

// Cuts `name` into pieces {text, start, end, nodeId}; nodeId is null for inert text.
// On equal widths the LATER node wins: children are emitted after their part.
export function sliceName(name, nodes) {
  const owner = new Array(name.length).fill(null)
  const width = new Array(name.length).fill(Infinity)
  for (const node of nodes || []) {
    if (!node.span) continue
    const [start, end] = node.span
    const w = end - start
    for (let i = Math.max(0, start); i < Math.min(end, name.length); i += 1) {
      if (w <= width[i]) {
        width[i] = w
        owner[i] = node.id
      }
    }
  }
  const pieces = []
  let start = 0
  for (let i = 1; i <= name.length; i += 1) {
    if (i === name.length || owner[i] !== owner[start]) {
      // start/end are offsets in the WHOLE name: typography is decided over the
      // whole string, so callers ask nameTypography for the runs in this range.
      pieces.push({ text: name.slice(start, i), start, end: i, nodeId: owner[start] })
      start = i
    }
  }
  return pieces
}

// Nodes OPSIN gave no position; the page lists them so they stay reachable.
export function unplacedNodes(nodes) {
  return (nodes || []).filter((node) => !node.span)
}
