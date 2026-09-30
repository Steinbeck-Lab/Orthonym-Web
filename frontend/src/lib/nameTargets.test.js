// frontend/src/lib/nameTargets.test.js
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { isPart, nodeById, partOf, sliceName, unplacedNodes } from './nameTargets.js'

const NAME = '1,3,7-trimethyl-3,7-dihydro-1H-purine-2,6-dione'
const NODES = [
  { id: 'n0', parent: null, kind: 'substituent', span: [9, 15], lights: [0, 5, 9] },
  { id: 'n1', parent: 'n0', kind: 'locant', span: [0, 1], lights: [0] },
  { id: 'n2', parent: 'n0', kind: 'multiplier', span: [6, 9], lights: [0, 5, 9] },
  { id: 'n3', parent: null, kind: 'parent', span: [31, 37], lights: [1, 2] },
  { id: 'n4', parent: 'n3', kind: 'stereo', span: null, lights: [] },
]

test('sliceName rejoins to exactly the input name', () => {
  assert.equal(sliceName(NAME, NODES).map((p) => p.text).join(''), NAME)
})

test('each character belongs to the smallest node covering it', () => {
  const pieces = sliceName(NAME, [...NODES, { id: 'n5', parent: null, kind: 'token', span: [0, 15] }])
  assert.equal(pieces.find((p) => p.text === '1').nodeId, 'n1')
  assert.equal(pieces.find((p) => p.text === 'methyl').nodeId, 'n0')
})

test('glue outside every node is inert', () => {
  assert.equal(sliceName(NAME, NODES).find((p) => p.start === 1).nodeId, null)
})

test('partOf climbs to the nearest part', () => {
  assert.equal(partOf(NODES, 'n1').id, 'n0')
  assert.equal(partOf(NODES, 'n3').id, 'n3')
  assert.equal(isPart(nodeById(NODES, 'n2')), false)
})

test('nodeById returns null for a stale id', () => {
  assert.equal(nodeById(NODES, 'n99'), null)
  assert.equal(nodeById(NODES, null), null)
  assert.equal(nodeById(undefined, 'n0'), null)
})

test('unplaced nodes are listed', () => {
  assert.deepEqual(unplacedNodes(NODES).map((n) => n.id), ['n4'])
})

// Edge cases of the cutting rule. The backend gates spans, but the page must
// not break or mislabel text if one ever arrives odd.
test('on equal widths the later node wins (children are emitted after their part)', () => {
  const nodes = [
    { id: 'part', parent: null, kind: 'substituent', span: [0, 4] },
    { id: 'child', parent: 'part', kind: 'locant', span: [0, 4] },
  ]
  assert.deepEqual(sliceName('abcdef', nodes).map((p) => [p.text, p.nodeId]), [['abcd', 'child'], ['ef', null]])
})

test('a zero-length span owns nothing and cuts nothing', () => {
  const nodes = [{ id: 'z', parent: null, kind: 'token', span: [3, 3] }]
  assert.deepEqual(sliceName('abcdef', nodes).map((p) => [p.text, p.nodeId]), [['abcdef', null]])
})

test('spans outside the name are clamped to it and the pieces still rejoin', () => {
  const nodes = [
    { id: 'a', parent: null, kind: 'token', span: [-2, 2] },
    { id: 'b', parent: null, kind: 'token', span: [4, 99] },
    { id: 'c', parent: null, kind: 'token', span: [50, 60] },
  ]
  const pieces = sliceName('abcdef', nodes)
  assert.equal(pieces.map((p) => p.text).join(''), 'abcdef')
  assert.deepEqual(pieces.map((p) => p.nodeId), ['a', null, 'b'])
})

test('an empty name and an empty list are harmless', () => {
  assert.deepEqual(sliceName('', []), [])
  assert.deepEqual(sliceName('ab', undefined).map((p) => p.nodeId), [null])
})
