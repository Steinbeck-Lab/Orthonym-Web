import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import { hiddenAt, revealSteps } from './classroom.js'
import { sliceName } from './nameTargets.js'

const R = JSON.parse(readFileSync(new URL('./compareNodes.fixture.json', import.meta.url), 'utf8'))
const stepsFor = (key) => revealSteps(sliceName(R[key].name, R[key].nodes), R[key].nodes)

test('the reveal follows the written order', () => {
  assert.deepEqual(stepsFor('propan-1-ol'), ['n0', 'n2', 'n1'])
  assert.deepEqual(stepsFor('2,2-dimethylbutane'), ['n1', 'n2', 'n3', 'n0', 'n4'])
})

test('a part that owns two pieces is one step', () => {
  const pieces = [
    { start: 0, end: 2, nodeId: 'a' },
    { start: 2, end: 3, nodeId: null },
    { start: 3, end: 5, nodeId: 'a' },
    { start: 5, end: 7, nodeId: 'b' },
  ]
  assert.deepEqual(revealSteps(pieces, [{ id: 'a', span: [0, 5] }, { id: 'b', span: [5, 7] }]), ['a', 'b'])
})

test('a part with no place in the name comes after every placed one', () => {
  const pieces = [{ start: 0, end: 4, nodeId: 'p' }]
  const nodes = [{ id: 'u', span: null }, { id: 'p', span: [0, 4] }]
  assert.deepEqual(revealSteps(pieces, nodes), ['p', 'u'])
})

test('step 0 hides everything, the last step hides nothing', () => {
  const steps = stepsFor('propan-1-ol')
  assert.equal(hiddenAt(steps, 0).size, steps.length)
  assert.deepEqual([...hiddenAt(steps, 1)].sort(), ['n1', 'n2'])
  assert.equal(hiddenAt(steps, steps.length).size, 0)
})

test('a detail line that names a hidden part gives it away', async () => {
  const { lineGivesAway } = await import('./classroom.js')
  // Caffeine: the N3 locant's line mentions hydrogen before "dihydro" shows.
  assert.equal(lineGivesAway('the name puts a hydrogen on the N3 atom', ['dihydro']), true)
  assert.equal(lineGivesAway('Position 2 — this group is attached at position 2.', ['methyl', 'butane']), false)
  assert.equal(lineGivesAway('part of methylpropyl', ['methyl']), true)
  // Short labels (locants, "di") are too common to judge; they never trigger.
  assert.equal(lineGivesAway('attached at position 2', ['2', 'di']), false)
  assert.equal(lineGivesAway('anything', []), false)
})
