import assert from 'node:assert/strict'
import { test } from 'node:test'

import { highlightTargets, shouldHighlight } from './useAtomHighlight.js'

// A segment tree shaped like the /explain response: an owning parent with a
// referential child that carries highlight_atoms but no atoms of its own.
const DATA = {
  segments: [
    {
      label: 'cyclohexan',
      atom_indices: [0, 1, 2, 3, 4, 5],
      highlight_atoms: [],
      children: [
        { label: 'hydro', atom_indices: [], highlight_atoms: [2, 3], children: [] },
      ],
    },
  ],
}

test('an owning segment highlights the atoms it owns', () => {
  assert.deepEqual([...highlightTargets(DATA, '0')].sort((a, b) => a - b), [0, 1, 2, 3, 4, 5])
})

test('a referential segment falls back to highlight_atoms', () => {
  // A hydro prefix owns no atoms. Without the fallback its atom_indices is
  // empty, highlightTargets returns null, and pointing at it goes dark --
  // silently, since nothing errors.
  assert.deepEqual([...highlightTargets(DATA, '0.0')], [2, 3])
})

test('no active path highlights nothing', () => {
  assert.equal(highlightTargets(DATA, null), null)
  assert.equal(highlightTargets(null, '0'), null)
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

test('when a segment has both, highlight_atoms wins over atom_indices', () => {
  // A part can own atoms and still point at a narrower set to light; preferring
  // the owned set would light the whole ring for a locant inside it.
  const both = {
    segments: [{ label: 'x', atom_indices: [0, 1, 2, 3], highlight_atoms: [1, 2], children: [] }],
  }
  assert.deepEqual([...highlightTargets(both, '0')].sort((a, b) => a - b), [1, 2])
})
