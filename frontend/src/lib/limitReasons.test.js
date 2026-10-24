import { strict as assert } from 'node:assert'
import { test } from 'node:test'

import { limitReasonFor } from './limitReasons.js'

test('every known code gets its sentence', () => {
  assert.match(limitReasonFor({ status: 'abstain', limit_code: 'UNSUPPORTED_RING_SYSTEM' }), /declines rather than guess/)
  assert.match(limitReasonFor({ status: 'abstain', limit_code: 'withheld_unchecked' }), /Turn best effort on/)
  for (const code of [
    'WILDCARD_ATOMS',
    'UNSUPPORTED_ELEMENT',
    'ISOLATED_ATOM',
    'STRUCTURE_TOO_LARGE',
    'UNNAMEABLE',
    'NO_VERIFIED_PIN',
  ]) {
    const reason = limitReasonFor({ status: 'abstain', limit_code: code })
    assert.ok(reason && !reason.startsWith('Reason code'), code)
  }
})

test('an unknown code shows the raw code, never nothing', () => {
  assert.equal(limitReasonFor({ status: 'abstain', limit_code: 'NEW_CODE' }), 'Reason code: NEW_CODE')
})

test('an error row gets no reason: its own message already says what failed', () => {
  assert.equal(limitReasonFor({ status: 'error', limit_code: 'timeout' }), null)
})

test('a named row or a row with no code gets no reason', () => {
  assert.equal(limitReasonFor({ status: 'pin', limit_code: 'UNNAMEABLE' }), null)
  assert.equal(limitReasonFor({ status: 'abstain', limit_code: null }), null)
})

test('the size and PIN sentences claim no more than the engine does', () => {
  // The engine refuses nothing for its size; it labels an UNNAMED input with
  // more than 125 heavy atoms. And NO_VERIFIED_PIN can be a verified
  // systematic name, so the sentence must not say "could not verify it".
  assert.equal(
    limitReasonFor({ status: 'abstain', limit_code: 'STRUCTURE_TOO_LARGE' }),
    'The engine found no name for this structure, which has more than 125 heavy atoms.'
  )
  assert.equal(
    limitReasonFor({ status: 'abstain', limit_code: 'NO_VERIFIED_PIN' }),
    'The engine built a name, but not a verified preferred IUPAC name, so it is not shown.'
  )
})
