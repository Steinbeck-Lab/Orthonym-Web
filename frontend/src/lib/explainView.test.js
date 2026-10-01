// What the /explain page decides to show, on REAL explain responses.
// explainResponses.fixture.json holds responses made by the v2 backend's own
// explain_name / explain_molecule (OPSIN's stored traces stand in for the JVM;
// the drawing is reduced to a placeholder because only the logic is under test).
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

import { explainPhase, detailNotes, pieceMark, tabStops } from './explainView.js'
import { nodeById, partOf, sliceName, unplacedNodes } from './nameTargets.js'
import { highlightTargets } from './useAtomHighlight.js'

const REAL = JSON.parse(readFileSync(new URL('./explainResponses.fixture.json', import.meta.url), 'utf8'))
const CAFFEINE = REAL['name:1,3,7-trimethyl-3,7-dihydro-1H-purine-2,6-dione']
const IBU_SMILES = REAL['smiles:CC(C)Cc1ccc(cc1)C(C)C(=O)O']
const TRANS = REAL['name:(+-)-trans-4-methylcyclohexan-1-ol']
const FAILURE = REAL['name:nonsenseane']
const OK = Object.entries(REAL).filter(([, r]) => !r.error)

test('the fixture is what it claims: real responses, one failure, one remap', () => {
  assert.ok(OK.length >= 6)
  assert.equal(FAILURE.svg, null)
  assert.deepEqual(IBU_SMILES.nodes.filter((n) => n.atoms_unmapped).map((n) => n.label).sort(), ['2', 'methyl', 'propyl'])
})

test('on every real response the pieces rejoin and every spanned node owns a piece', () => {
  for (const [key, r] of OK) {
    const pieces = sliceName(r.name, r.nodes)
    assert.equal(pieces.map((p) => p.text).join(''), r.name, key)
    const reached = new Set(pieces.map((p) => p.nodeId))
    for (const node of r.nodes) {
      if (node.span) assert.ok(reached.has(node.id), `${key}: ${node.label} is unreachable`)
    }
  }
})

test('caffeine: hovering the locant 1 lights one atom, inside the methyl part', () => {
  const one = sliceName(CAFFEINE.name, CAFFEINE.nodes).find((p) => p.text === '1' && p.start === 0)
  const node = nodeById(CAFFEINE.nodes, one.nodeId)
  assert.equal(node.kind, 'locant')
  assert.equal(highlightTargets(CAFFEINE, node.id).size, 1)
  assert.equal(partOf(CAFFEINE.nodes, node.id).label, 'methyl')
})

test('a whole-request failure is one message, not a result', () => {
  assert.equal(explainPhase(FAILURE), 'error')
  assert.equal(explainPhase({ ...FAILURE, name: null }), 'error')
})

test('a result with a drawing is a result, even with an error beside it (TNT case)', () => {
  assert.equal(explainPhase({ ...CAFFEINE, nodes: [], error: 'Could not explain this name.' }), 'success')
  for (const [key, r] of OK) assert.equal(explainPhase(r), 'success', key)
})

test('a mark that lights nothing says so; it does not claim to point at atoms', () => {
  const trans = TRANS.nodes.find((n) => n.kind === 'stereo' && n.label === 'trans')
  assert.equal(highlightTargets(TRANS, trans.id), null)
  const notes = detailNotes(TRANS.nodes, trans.id)
  assert.equal(notes.nothingLights, true)
  assert.equal(notes.notation, false)
})

test('notation that lights atoms keeps the notation note', () => {
  const one = CAFFEINE.nodes.find((n) => n.kind === 'locant')
  const notes = detailNotes(CAFFEINE.nodes, one.id)
  assert.equal(notes.notation, true)
  assert.equal(notes.nothingLights, false)
  assert.equal(notes.partLabel, 'methyl')
})

test('an unmapped node gets the unmapped note, not the nothing-lights note', () => {
  const methyl = IBU_SMILES.nodes.find((n) => n.label === 'methyl')
  const notes = detailNotes(IBU_SMILES.nodes, methyl.id)
  assert.equal(notes.unmapped, true)
  assert.equal(notes.nothingLights, false)
  assert.equal(notes.partLabel, null)
})

test('on every real response: nothingLights agrees with highlightTargets', () => {
  for (const [key, r] of OK) {
    for (const node of r.nodes) {
      const notes = detailNotes(r.nodes, node.id)
      const lit = highlightTargets(r, node.id) !== null
      assert.equal(notes.nothingLights, !lit && !node.atoms_unmapped, `${key}: ${node.label}`)
      assert.equal(notes.unmapped, Boolean(node.atoms_unmapped), `${key}: ${node.label}`)
    }
  }
})

test('detailNotes of a stale id is empty', () => {
  assert.deepEqual(detailNotes(CAFFEINE.nodes, 'n99'), {
    partLabel: null, nothingLights: false, notation: false, unmapped: false,
  })
})

test('only the part is marked as context, not its siblings', () => {
  const part = CAFFEINE.nodes.find((n) => n.kind === 'substituent')
  const sibling = CAFFEINE.nodes.find((n) => n.parent === part.id)
  const other = CAFFEINE.nodes.find((n) => n.kind === 'locant' && n.parent === part.id && n.id !== sibling.id)
  assert.equal(pieceMark({ nodeId: part.id }, sibling.id, part), 'context')
  assert.equal(pieceMark({ nodeId: other.id }, sibling.id, part), null)
  assert.equal(pieceMark({ nodeId: sibling.id }, sibling.id, part), 'active')
  assert.equal(pieceMark({ nodeId: part.id }, part.id, part), 'active')
  assert.equal(pieceMark({ nodeId: part.id }, null, null), null)
  assert.equal(pieceMark({ nodeId: null }, sibling.id, part), null)
})

test('punctuation inside a word-bearing node is not a tab stop; words and numbers are', () => {
  const pieces = [
    { text: '2', nodeId: 'a' }, { text: ',', nodeId: 'a' }, { text: '6', nodeId: 'a' },
    { text: '-', nodeId: null }, { text: 'dione', nodeId: 'b' },
  ]
  assert.deepEqual([...tabStops(pieces)].sort(), [0, 2, 4])
})

test('a node made only of punctuation keeps its first piece as a stop', () => {
  const pieces = [
    { text: '+-', nodeId: 'n1' }, { text: '-', nodeId: 'n1' }, { text: 'trans', nodeId: 'n2' },
  ]
  assert.deepEqual([...tabStops(pieces)].sort(), [0, 2])
})

test('real responses: every placed node keeps at least one keyboard stop, punctuation does not', () => {
  for (const [key, r] of OK) {
    const pieces = sliceName(r.name, r.nodes)
    const stops = tabStops(pieces)
    for (const node of r.nodes.filter((n) => n.span)) {
      assert.ok(pieces.some((p, i) => p.nodeId === node.id && stops.has(i)), `${key}: ${node.label} has no tab stop`)
    }
    for (const i of stops) assert.ok(pieces[i].nodeId, key)
  }
  const caffeine = sliceName(CAFFEINE.name, CAFFEINE.nodes)
  const punct = caffeine.filter((p, i) => p.nodeId && !/[\p{L}\p{N}]/u.test(p.text) && tabStops(caffeine).has(i))
  assert.deepEqual(punct, [])
})

test('unplaced nodes are still listed on real responses', () => {
  for (const [, r] of OK) assert.deepEqual(unplacedNodes(r.nodes), r.nodes.filter((n) => !n.span))
})
