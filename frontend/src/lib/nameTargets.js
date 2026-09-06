// Flattens the segment tree into the spans that exist in the name, innermost
// first so a locant inside a part wins the hover over the part around it.
export function nameTargets(segments) {
  const out = []
  segments.forEach((segment, index) => {
    if (segment.name_range) {
      out.push({ path: String(index), range: segment.name_range, depth: 0 })
    }
    segment.children.forEach((child, childIndex) => {
      if (child.name_range) {
        out.push({
          path: `${index}.${childIndex}`, range: child.name_range, depth: 1,
        })
      }
    })
  })
  return out.sort((a, b) => b.depth - a.depth || a.range[0] - b.range[0])
}

// Cuts `name` into a flat run of pieces, each either inert text or a target.
export function sliceName(name, targets) {
  const owner = new Array(name.length).fill(null)
  for (const target of targets) {
    for (let i = target.range[0]; i < target.range[1]; i += 1) {
      if (owner[i] === null) owner[i] = target.path
    }
  }
  const pieces = []
  let start = 0
  for (let i = 1; i <= name.length; i += 1) {
    if (i === name.length || owner[i] !== owner[start]) {
      // `start`/`end` are the piece's offsets in the WHOLE name. The
      // typography of a name is decided over the whole string (a
      // stereodescriptor cut in half parses as nothing), so a caller that
      // wants both must ask nameTypography for the runs inside this range.
      pieces.push({ text: name.slice(start, i), path: owner[start], start, end: i })
      start = i
    }
  }
  return pieces
}
