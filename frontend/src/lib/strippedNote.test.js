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
