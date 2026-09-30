import { test } from 'node:test'
import assert from 'node:assert/strict'
import { nameTargets, sliceName } from './nameTargets.js'

const NAME = '1,3,7-trimethyl-3,7-dihydro-1H-purine-2,6-dione'
const SEGMENTS = [
  { name_range: [0, 16], children: [
    { locant: '1', name_range: [0, 1] },
    { locant: '3', name_range: [2, 3] },
    { locant: '7', name_range: [4, 5] },
  ] },
  { name_range: [31, 37], children: [] },
]

test('sliceName rejoins to exactly the input name', () => {
  const pieces = sliceName(NAME, nameTargets(SEGMENTS))
  assert.equal(pieces.map((p) => p.text).join(''), NAME)
})

test('a child wins the hover over the part around it', () => {
  const pieces = sliceName(NAME, nameTargets(SEGMENTS))
  const first = pieces.find((p) => p.text === '1')
  assert.equal(first.path, '0.0')
})

test('a child with no name_range is simply not a target', () => {
  const segs = [{ name_range: [0, 5], children: [{ locant: '1', name_range: null }] }]
  const targets = nameTargets(segs)
  assert.equal(targets.length, 1)
  assert.equal(targets[0].path, '0')
})

test('every piece carries the offsets of its own text in the whole name', () => {
  // Explain.jsx asks for typography over [start, end) and reads name[start - 1]
  // for its wrap rule. Offsets that do not point at the piece's own text put
  // the styling on the wrong characters.
  const pieces = sliceName(NAME, nameTargets(SEGMENTS))
  let cursor = 0
  for (const piece of pieces) {
    assert.equal(piece.start, cursor, 'pieces are contiguous')
    assert.equal(NAME.slice(piece.start, piece.end), piece.text)
    cursor = piece.end
  }
  assert.equal(cursor, NAME.length)
})
