import { strict as assert } from 'node:assert'
import { test } from 'node:test'

import { limitReasonFor } from './limitReasons.js'

test('every known code gets its sentence', () => {
  assert.match(limitReasonFor({ status: 'abstain', limit_code: 'UNSUPPORTED_RING_SYSTEM' }), /declines rather than guess/)
  assert.match(limitReasonFor({ status: 'abstain', limit_code: 'withheld_unchecked' }), /Turn best effort on/)
  assert.match(limitReasonFor({ status: 'error', limit_code: 'timeout' }), /too long/)
  for (const code of [
    'WILDCARD_ATOMS',
    'UNSUPPORTED_ELEMENT',
    'ISOLATED_ATOM',
    'STRUCTURE_TOO_LARGE',
    'UNNAMEABLE',
    'NO_VERIFIED_PIN',
    'engine_error',
  ]) {
    const reason = limitReasonFor({ status: 'abstain', limit_code: code })
    assert.ok(reason && !reason.startsWith('Reason code'), code)
  }
})

test('an unknown code shows the raw code, never nothing', () => {
  assert.equal(limitReasonFor({ status: 'abstain', limit_code: 'NEW_CODE' }), 'Reason code: NEW_CODE')
})

test('a named row or a row with no code gets no reason', () => {
  assert.equal(limitReasonFor({ status: 'pin', limit_code: 'UNNAMEABLE' }), null)
  assert.equal(limitReasonFor({ status: 'abstain', limit_code: null }), null)
})
