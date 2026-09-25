import { strict as assert } from 'node:assert'
import { test } from 'node:test'

import { MISMATCH_LABEL, STATE_LABEL, STATE_SHORT, UNCHECKED_LABEL, stateLabelFor } from './statuses.js'

test('a best_effort row with no round trip here says so, whatever its engine tier', () => {
  // Whatever built it -- a demoted pin or fallback, or a genuine best_effort --
  // and on a batch row that carries no tier, the one true claim is that no
  // round trip ran here.
  for (const tier of ['pin_verified', 'systematic_verified', 'pin_unverified', 'best_effort', undefined]) {
    assert.equal(stateLabelFor({ status: 'best_effort', tier, roundtrip_smiles: null }), UNCHECKED_LABEL, tier)
  }
})

test('a best_effort row with a round trip keeps the general-engine label', () => {
  assert.equal(
    stateLabelFor({ status: 'best_effort', tier: 'best_effort', roundtrip_smiles: 'CCO' }),
    'Best-effort name from the general engine',
  )
})

test('a best_effort row whose round trip did not match says so, whatever its engine tier', () => {
  // A demoted pin or fallback is not "from the general engine"; a different
  // structure on the read-back is true of every such row.
  for (const tier of ['pin_verified', 'systematic_verified', 'best_effort', undefined]) {
    assert.equal(
      stateLabelFor({ status: 'best_effort', tier, roundtrip_smiles: 'CCCO', roundtrip_match: false }),
      MISMATCH_LABEL,
      tier,
    )
  }
})

test('every other status reads its own label', () => {
  assert.equal(stateLabelFor({ status: 'fallback', roundtrip_smiles: 'CCO' }), 'Verified name, preferred status not certified')
  assert.equal(stateLabelFor({ status: 'pin', roundtrip_smiles: 'CCO' }), STATE_LABEL.pin)
})

test('no label or short word calls a name unverified or unconfirmed', () => {
  // Paper reviewer issue 2: "OPSIN did not confirm it" sat beside a green
  // round trip on every sixth ChEBI-like name.
  for (const text of [...Object.values(STATE_LABEL), ...Object.values(STATE_SHORT), UNCHECKED_LABEL]) {
    if (text) assert.ok(!/unverified|did not confirm|could not confirm|not confirmed/i.test(text), text)
  }
  assert.equal(STATE_SHORT.best_effort, 'BEST EFFORT')
  assert.equal(STATE_SHORT.error, 'ERROR')
})
