import { strict as assert } from 'node:assert'
import { test } from 'node:test'

import { MISMATCH_LABEL, STATE_LABEL, STATE_SHORT, TIER_ORDER, UNCHECKED_LABEL, lampTitleFor, stateLabelFor } from './statuses.js'

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

test('every lamp says how its name was made, in the tier word it wears', () => {
  for (const status of TIER_ORDER) {
    const title = lampTitleFor(status)
    assert.ok(title.startsWith(`${STATE_SHORT[status]}: `), title)
    assert.ok(title.length > STATE_SHORT[status].length + 10, title)
  }
  assert.equal(lampTitleFor(undefined), undefined, 'a pending tile has no tier to explain')
})

test('a demoted row\'s lamp does not claim the general engine built it', () => {
  // Batch rows carry no tier, so an unchecked or mismatched best_effort row
  // may be a demoted pin: its tooltip says what is true of every such row.
  const unchecked = { status: 'best_effort', roundtrip_smiles: null }
  const mismatch = { status: 'best_effort', roundtrip_smiles: 'CCCO', roundtrip_match: false }
  assert.equal(lampTitleFor('best_effort', unchecked), `BEST EFFORT: ${UNCHECKED_LABEL}.`)
  assert.equal(lampTitleFor('best_effort', mismatch), `BEST EFFORT: ${MISMATCH_LABEL}.`)
  const genuine = { status: 'best_effort', roundtrip_smiles: 'CCO', roundtrip_match: true }
  assert.match(lampTitleFor('best_effort', genuine), /general engine/)
})
