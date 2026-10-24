import assert from 'node:assert/strict'
import { test } from 'node:test'
import { verdictHow } from './verdicts.js'

test('a compared pair says it was compared', () => {
  assert.equal(
    verdictHow({ verdict: 'same', input_inchikey: 'A', claimed_inchikey: 'A' }),
    'OPSIN read your name; the two structures were compared by InChIKey, which counts tautomers as one structure.'
  )
})

test('an unreadable name says there was nothing to compare', () => {
  assert.equal(
    verdictHow({ verdict: 'unreadable' }),
    'OPSIN could not read this name, so there is no structure to compare.'
  )
})

test('"Could not compare" names the side with no InChIKey, and claims no comparison', () => {
  assert.equal(
    verdictHow({ verdict: 'uncomparable', input_inchikey: null, claimed_inchikey: 'B' }),
    'OPSIN read your name, but no InChIKey could be made for your structure, so the two could not be compared.'
  )
  assert.equal(
    verdictHow({ verdict: 'uncomparable', input_inchikey: 'A', claimed_inchikey: null }),
    'OPSIN read your name, but no InChIKey could be made for the structure it describes, so the two could not be compared.'
  )
})
