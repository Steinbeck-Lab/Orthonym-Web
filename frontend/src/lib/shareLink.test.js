import { strict as assert } from 'node:assert'
import { test } from 'node:test'

import { buildShareHash, readShareHash } from './shareLink.js'

test('round-trips a SMILES with every character that needs encoding', () => {
  const smiles = 'C/C=C\\C#N.[nH]1cccc1 %10+'
  assert.deepEqual(readShareHash(buildShareHash({ smiles })), { smiles })
})

test('round-trips a name with brackets, commas and primes', () => {
  const name = "(2S)-2-amino-3-(1H-indol-3-yl)propanoic acid; 4',5-di"
  assert.deepEqual(readShareHash(buildShareHash({ name })), { name })
})

test('the hash starts with # and names its field', () => {
  assert.equal(buildShareHash({ smiles: 'CCO' }), '#smiles=CCO')
})

test('a hand-typed + stays a charge, not a space', () => {
  assert.deepEqual(readShareHash('#smiles=[NH4+]'), { smiles: '[NH4+]' })
})

test('a malformed percent escape reads as null, not a crash', () => {
  assert.equal(readShareHash('#smiles=%E0%A4%A'), null)
})

test('an empty or junk hash reads as null', () => {
  for (const h of ['', '#', '#abc', '#=', '#=CCO']) assert.equal(readShareHash(h), null, h)
})

test('an over-long hash is refused', () => {
  assert.equal(readShareHash('#smiles=' + 'C'.repeat(4001)), null)
})
