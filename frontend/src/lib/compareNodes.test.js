import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import { diffNodes } from './compareNodes.js'

// Real /api/explain-name answers, captured from the stack (2026-10-24).
const R = JSON.parse(readFileSync(new URL('./compareNodes.fixture.json', import.meta.url), 'utf8'))
const nodes = (name) => R[name].nodes
const ids = (set) => [...set].sort()

test('the same name has nothing to mark', () => {
  const { a, b } = diffNodes(nodes('ethanol'), nodes('ethanol'))
  assert.deepEqual([ids(a), ids(b)], [[], []])
})

test('propan-1-ol vs propan-2-ol: only the locants differ', () => {
  const { a, b } = diffNodes(nodes('propan-1-ol'), nodes('propan-2-ol'))
  assert.deepEqual(ids(a), ['n2'])
  assert.deepEqual(ids(b), ['n2'])
})

test('a repeated part is counted, not just present: one extra "2" and the "di"', () => {
  const { a, b } = diffNodes(nodes('2-methylbutane'), nodes('2,2-dimethylbutane'))
  assert.deepEqual(ids(a), [])
  // n1 (the first "2", by position) is the partner of 2-methylbutane's "2".
  assert.deepEqual(ids(b), ['n2', 'n3'])
})

test('an empty side marks every node of the other', () => {
  assert.deepEqual(ids(diffNodes([], []).a), [])
  const { a, b } = diffNodes([], nodes('ethanol'))
  assert.deepEqual([ids(a), ids(b)], [[], ['n0', 'n1']])
})

test('a node with no span is matched after every placed one', () => {
  const A = [{ id: 'x', kind: 'locant', label: '1', span: null }, { id: 'y', kind: 'locant', label: '1', span: [0, 1] }]
  const B = [{ id: 'z', kind: 'locant', label: '1', span: [3, 4] }]
  assert.deepEqual(ids(diffNodes(A, B).a), ['x'])
})
