import assert from 'node:assert/strict'
import { test } from 'node:test'
import { strippedNote } from './strippedNote.js'

test('a stripped row says what was removed', () => {
  assert.equal(strippedNote({ stripped_from: 'CCO.Cl', removed: 'Cl' }), 'Named after removing: Cl')
})

test('an ordinary row says nothing', () => {
  assert.equal(strippedNote({ smiles: 'CCO' }), null)
  assert.equal(strippedNote(null), null)
})

test('never "removing: null"', () => {
  assert.equal(strippedNote({ stripped_from: 'CCO.Cl', removed: null }), null)
})

test('a switch that could not run says so', () => {
  assert.equal(
    strippedNote({ strip_skipped: true }),
    'Salts not stripped: this structure could not be split into fragments, so all of it was named.'
  )
})

test('a stripped row shows what was typed, and its picture says it is a fragment', async () => {
  const { typedInput, structureAlt } = await import('./strippedNote.js')
  const stripped = { smiles: 'CCO', stripped_from: 'CCO.Cl' }
  assert.equal(typedInput(stripped), 'CCO.Cl')
  assert.equal(typedInput({ smiles: 'CCO' }), 'CCO')
  assert.equal(structureAlt(stripped), 'named: the largest fragment of "CCO.Cl"')
  assert.equal(structureAlt({ smiles: 'CCO' }), 'you entered, "CCO"')
})
