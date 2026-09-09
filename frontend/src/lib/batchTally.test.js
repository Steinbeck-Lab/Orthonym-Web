import { strict as assert } from 'node:assert'
import { test } from 'node:test'

import { outcomeMessage, tallySummary, tierTally } from './batchTally.js'

test('tierTally reports the ladder in order, strongest first', () => {
  // Deliberately out of order and with a gap, which is what a real job sends.
  const rows = tierTally({ error: 2, pin: 9, abstain: 4 })
  assert.deepEqual(
    rows.map((r) => r.status),
    ['pin', 'abstain', 'error']
  )
  assert.deepEqual(
    rows.map((r) => r.label),
    ['PIN', 'NO NAME', 'BAD INPUT']
  )
  assert.deepEqual(
    rows.map((r) => r.count),
    [9, 4, 2]
  )
})

test('tierTally carries the CSS class each tier already uses', () => {
  // best_effort -> best-effort is the underscore/hyphen crossing that
  // statuses.js exists to hold in one place; a tally that got it wrong would
  // draw the wrong rule under the count.
  const [row] = tierTally({ best_effort: 3 })
  assert.equal(row.className, 'best-effort')
  assert.equal(row.label, 'UNVERIFIED')
})

test('tierTally omits a tier with no rows rather than showing a zero', () => {
  // On a running job "0 bad input" and "no bad input counted yet" are
  // different claims, and only the second one is true.
  const rows = tierTally({ pin: 5, fallback: 0 })
  assert.deepEqual(
    rows.map((r) => r.status),
    ['pin']
  )
})

test('tierTally keeps an unknown tier instead of dropping it', () => {
  // If the backend grows a sixth tier, a batch of them must not silently
  // vanish from the count.
  const rows = tierTally({ pin: 1, something_new: 7 })
  assert.deepEqual(
    rows.map((r) => [r.status, r.count]),
    [
      ['pin', 1],
      ['something_new', 7],
    ]
  )
})

test('tierTally survives a missing counts object', () => {
  // The first poll of a fresh job carries none.
  assert.deepEqual(tierTally(undefined), [])
  assert.deepEqual(tierTally(null), [])
  assert.deepEqual(tierTally({}), [])
})

test('tallySummary counts an abstain as unnamed, never as named', () => {
  // The whole point of this module. An abstain ships no name, so the
  // submitter must see it in the "not named" figure -- while the per-tier
  // list keeps it distinct from an unreadable input.
  const s = tallySummary({ pin: 6, fallback: 2, best_effort: 1, abstain: 4, error: 3 })
  assert.equal(s.named, 9)
  assert.equal(s.unnamed, 7)
  assert.equal(s.counted, 16)
})

test('tallySummary counts an unverified best-effort name as named', () => {
  // It IS a name. Its tier says OPSIN did not confirm it, and the rule under
  // it says so too; calling it "not named" would be a different lie.
  assert.deepEqual(tallySummary({ best_effort: 5 }), { named: 5, unnamed: 0, counted: 5 })
})

test('tallySummary counts out of what it has, not out of the job total', () => {
  // While a job runs the counts are partial. Reporting them against `total`
  // would show a shortfall that is only work still in progress.
  assert.equal(tallySummary({ pin: 2 }).counted, 2)
  assert.deepEqual(tallySummary(undefined), { named: 0, unnamed: 0, counted: 0 })
})

test('tallySummary files an unknown tier under unnamed', () => {
  // Conservative on purpose: claiming a name the frontend does not recognise
  // would overstate the run.
  assert.deepEqual(tallySummary({ something_new: 4 }), { named: 0, unnamed: 4, counted: 4 })
})

test('outcomeMessage reads the whole run back in words', () => {
  assert.equal(
    outcomeMessage({ pin: 130, fallback: 125, abstain: 2 }, { finished: true }),
    '255 of 257 molecules were named: 130 verified Preferred IUPAC Names and ' +
      '125 verified fallback names. The engine declined to name 2 rather than guess.'
  )
})

test('outcomeMessage says "all" when nothing was missed', () => {
  assert.equal(
    outcomeMessage({ pin: 130, fallback: 125 }, { finished: true }),
    'All 255 molecules were named: 130 verified Preferred IUPAC Names and ' +
      '125 verified fallback names.'
  )
})

test('outcomeMessage gives an abstain its own sentence, never a failure list', () => {
  // An abstain is the engine working correctly. Listing it beside an
  // unreadable input would be the conflation PRODUCT.md forbids.
  const m = outcomeMessage({ pin: 4, abstain: 3, error: 2 }, { finished: true })
  assert.equal(
    m,
    '4 of 9 molecules were named: 4 verified Preferred IUPAC Names. ' +
      'The engine declined to name 3 rather than guess. ' +
      '2 inputs could not be read at all.'
  )
})

test('outcomeMessage never claims an aggregate round-trip', () => {
  // A pin row can carry no roundtrip_smiles at all -- RoundTripCell has an
  // "unavailable" state for exactly that -- so a sentence built from tier
  // counts must not assert that OPSIN read anything back.
  const m = outcomeMessage({ pin: 10 }, { finished: true })
  assert.ok(!/OPSIN|read .* back|round-?trip/i.test(m), m)
})

test('outcomeMessage marks a running job as partial', () => {
  assert.equal(
    outcomeMessage({ pin: 88, fallback: 86, abstain: 1 }, { finished: false }),
    'So far, 174 of 175 molecules were named: 88 verified Preferred IUPAC Names ' +
      'and 86 verified fallback names. The engine declined to name 1 rather than guess.'
  )
})

test('outcomeMessage counts against what was counted, not the job total', () => {
  // A job stopped at 100 of 400 has 300 molecules nobody looked at. Reporting
  // them as misses would be a straight falsehood.
  const m = outcomeMessage({ pin: 95, error: 5 }, { finished: true })
  assert.ok(m.includes('95 of 100 molecules'), m)
  assert.ok(!m.includes('400'), m)
})

test('outcomeMessage keeps its grammar singular where it should', () => {
  assert.equal(
    outcomeMessage({ pin: 1 }, { finished: true }),
    'All 1 molecule was named: 1 verified Preferred IUPAC Name.'
  )
  assert.equal(
    outcomeMessage({ abstain: 1 }, { finished: true }),
    // "zero ... were", agreeing with the count before "of": 0 takes the plural.
    '0 of 1 molecule were named. The engine declined to name 1 rather than guess.'
  )
  assert.equal(
    outcomeMessage({ error: 1 }, { finished: true }),
    '0 of 1 molecule were named. 1 input could not be read at all.'
  )
})

test('outcomeMessage returns null before anything is counted', () => {
  assert.equal(outcomeMessage(undefined, { finished: false }), null)
  assert.equal(outcomeMessage({}, { finished: true }), null)
})
