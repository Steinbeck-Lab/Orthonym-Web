import { strict as assert } from 'node:assert'
import { test } from 'node:test'

import { splitLines } from './parseLines.js'

test('splitLines trims each line and drops blank ones', () => {
  const { lines } = splitLines('  CCO  \n\n   \nCCC\n', 10)
  assert.deepEqual(lines, ['CCO', 'CCC'])
})

test('splitLines reports the true total, not the truncated one', () => {
  // The count the user is told must be what they pasted. Reporting the
  // capped number would hide the fact that lines were dropped.
  const { lines, total, truncated } = splitLines('a\nb\nc\nd', 2)
  assert.deepEqual(lines, ['a', 'b'])
  assert.equal(total, 4)
  assert.equal(truncated, true)
})

test('splitLines does not claim truncation when everything fits', () => {
  const { total, truncated } = splitLines('a\nb', 2)
  assert.equal(total, 2)
  assert.equal(truncated, false)
})

test('splitLines handles empty and whitespace-only text', () => {
  assert.deepEqual(splitLines('', 10).lines, [])
  assert.deepEqual(splitLines('   \n\t\n', 10).lines, [])
  assert.equal(splitLines('   ', 10).total, 0)
})

test('splitLines handles CRLF line endings', () => {
  // A file pasted from Windows arrives with \r\n; a trailing \r would ride
  // into the SMILES or the name and break the lookup with no visible cause.
  assert.deepEqual(splitLines('CCO\r\nCCC\r\n', 10).lines, ['CCO', 'CCC'])
})

test('splitLines treats a missing value as no text', () => {
  // A cleared field can hand over null or undefined; String(undefined) would
  // turn it into the one line "undefined".
  for (const missing of [null, undefined]) {
    assert.deepEqual(splitLines(missing, 10), { lines: [], total: 0, truncated: false })
  }
})
