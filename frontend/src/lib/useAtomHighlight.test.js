import assert from 'node:assert/strict'
import { test } from 'node:test'

import { highlightTargets, shouldHighlight } from './useAtomHighlight.js'

const DATA = {
  nodes: [
    { id: 'n0', parent: null, kind: 'parent', owns: [0, 1, 2, 3, 4, 5], lights: [0, 1, 2, 3, 4, 5] },
    { id: 'n1', parent: 'n0', kind: 'hydro', owns: [], lights: [2, 3] },
    { id: 'n2', parent: 'n0', kind: 'stereo', owns: [], lights: [] },
  ],
}

test('a node lights its lights', () => {
  assert.deepEqual([...highlightTargets(DATA, 'n0')].sort((a, b) => a - b), [0, 1, 2, 3, 4, 5])
  assert.deepEqual([...highlightTargets(DATA, 'n1')], [2, 3])
})

test('a node with nothing to light highlights nothing', () => {
  assert.equal(highlightTargets(DATA, 'n2'), null)
})

test('no active id highlights nothing', () => {
  assert.equal(highlightTargets(DATA, null), null)
  assert.equal(highlightTargets(null, 'n0'), null)
  assert.equal(highlightTargets(DATA, 'n99'), null)
})

test('an element lights up only when every atom it references is in the set', () => {
  const target = new Set([7, 11])
  // A bond wholly inside the region.
  assert.equal(shouldHighlight('bond-10 atom-7 atom-11', target), true)
  // A bond leaving the region stays neutral, so the edge reads as a clean
  // boundary rather than a half-lit connecting bond. Loosening `every` to
  // `some` is a one-word change with an obvious visual consequence.
  assert.equal(shouldHighlight('bond-12 atom-7 atom-99', target), false)
})

test('an element referencing no atoms never lights up', () => {
  // RDKit's background rect and similar have no atom-N class. Without the
  // refs.length check, `[].every(...)` is vacuously true and the whole
  // drawing would go solid.
  assert.equal(shouldHighlight('background', new Set([1])), false)
  assert.equal(shouldHighlight(null, new Set([1])), false)
})

test('a null target set highlights nothing', () => {
  assert.equal(shouldHighlight('bond-10 atom-7 atom-11', null), false)
})

test('a node lights its lights, not everything it owns', () => {
  // A part can own atoms and still point at a narrower set to light; lighting
  // the owned set would light the whole ring for a locant inside it.
  const both = {
    nodes: [{ id: 'n0', parent: null, kind: 'suffix', owns: [0, 1, 2, 3], lights: [1, 2] }],
  }
  assert.deepEqual([...highlightTargets(both, 'n0')].sort((a, b) => a - b), [1, 2])
})
