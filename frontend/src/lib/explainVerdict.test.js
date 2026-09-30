import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

import { verdictKindFor, roundtripLine } from './explainVerdict.js'

// ---------------------------------------------------------------- verdictKind

test('a structure Orthonym named carries a real verdict', () => {
  assert.equal(verdictKindFor('smiles'), 'orthonym-verdict')
  assert.equal(verdictKindFor('draw'), 'orthonym-verdict')
})

test('a name the user typed carries no Orthonym verdict', () => {
  assert.equal(verdictKindFor('name'), 'user-supplied')
})

test('nothing explained yet claims nothing at all', () => {
  assert.equal(verdictKindFor(null), 'none')
  assert.equal(verdictKindFor(undefined), 'none')
})

// The bug this whole module exists for. The claim must follow the request the
// result CAME FROM, so that changing tabs afterwards -- which re-runs nothing --
// cannot rewrite a verdict that is already on screen.
test('the claim is a property of the request, so a later tab change cannot alter it', () => {
  // A SMILES was explained. Whatever tab the user clicks next, this result was
  // still produced by Orthonym and still owes its tier.
  const resultMode = 'smiles'
  for (const tabTheUserClicksNext of ['name', 'smiles', 'draw']) {
    assert.equal(
      verdictKindFor(resultMode),
      'orthonym-verdict',
      `a result fetched as SMILES must keep its verdict while the ${tabTheUserClicksNext} tab is selected`
    )
  }

  // And the reverse: a name the user supplied keeps its honest disclosure.
  for (const tabTheUserClicksNext of ['name', 'smiles', 'draw']) {
    assert.equal(
      verdictKindFor('name'),
      'user-supplied',
      `a user-supplied name must keep its disclosure while the ${tabTheUserClicksNext} tab is selected`
    )
  }
})

// --------------------------------------------------------------- roundtripLine

test('a confirmed round-trip reports the match AND the SMILES that proves it', () => {
  const line = roundtripLine({ status: 'pin', roundtrip_smiles: 'CCO', roundtrip_match: true })
  assert.equal(line.available, true)
  assert.equal(line.match, true)
  assert.equal(line.smiles, 'CCO')
  assert.match(line.result, /same molecule/)
  // Principle 1: the proof is the string, so it must survive into the output.
  assert.ok(line.smiles, 'the round-trip SMILES is the proof and must never be dropped')
})

test('a failed round-trip says so rather than going quiet', () => {
  const line = roundtripLine({ status: 'fallback', roundtrip_smiles: 'CCC', roundtrip_match: false })
  assert.equal(line.match, false)
  assert.match(line.result, /different molecule/)
  assert.equal(line.smiles, 'CCC')
})

test('a tier that claims a round-trip must not fall silent when the proof is missing', () => {
  for (const status of ['pin', 'fallback']) {
    const line = roundtripLine({ status, roundtrip_smiles: null })
    assert.ok(line, `${status} claims a round-trip, so a missing proof must be stated`)
    assert.equal(line.available, false)
    assert.match(line.result, /unavailable/)
  }
})

test('a tier that claims no round-trip stays silent when there is no proof', () => {
  // best_effort claims no verified tier, and its label already says when no
  // round trip ran here. Adding "unavailable" would report a check that was
  // never claimed.
  assert.equal(roundtripLine({ status: 'best_effort', roundtrip_smiles: null }), null)
})

test('a result with no name has no round-trip line', () => {
  assert.equal(roundtripLine(null), null)
  assert.equal(roundtripLine({ status: 'abstain' }), null)
  assert.equal(roundtripLine({ status: 'error' }), null)
})

test('one voice: the sentence is plain English and still carries the proof', () => {
  const line = roundtripLine({ status: 'pin', roundtrip_smiles: 'CCO', roundtrip_match: true })
  // The Learn/Expert switch was removed by MERGING the two spellings. If a
  // future edit drops either half, this is what fails: the plain-English claim
  // about what the check did, and the machine-readable proof beside it.
  assert.match(line.lead, /we read this name back/, 'the plain-English half of the merged voice')
  assert.equal(line.smiles, 'CCO', 'the technical half of the merged voice')
})

// ------------------------------------------------- the call site, not the unit
//
// The unit tests above cannot see WHICH variable Explain.jsx passes in, and
// that variable was the entire bug: the branch read the live input tab instead
// of the mode the displayed result was fetched with. A component test would
// catch it, but `npm test` is bare `node --test` with no transform, so a file
// containing JSX cannot be imported here at all.
//
// So this reads the source. It is a blunt instrument and deliberately the only
// one of its kind in the suite -- justified because the defect is invisible to
// every other tool available: it type-checks, it lints, it renders, and it is
// wrong.
test('Explain.jsx decides the claim from the result, never from the live tab', () => {
  const src = readFileSync(
    fileURLToPath(new URL('../pages/Explain.jsx', import.meta.url)),
    'utf8'
  )

  // Find the tier branch by the copy it guards, not by a line number.
  const marker = 'This breakdown is of the name'
  const at = src.indexOf(marker)
  assert.ok(at > 0, 'the user-supplied-name disclosure should still exist on /explain')

  // The ternary that chooses it sits just above that copy.
  const branch = src.slice(Math.max(0, at - 400), at)
  // Asserting the CALL, not the inline spelling. This is strictly stronger:
  // reintroducing the original bug as `verdictKindFor(mode)` would fail here,
  // where the negative guard below could not catch it -- once the rule is a
  // function call there is no `=== 'name'` literal left for it to match.
  assert.match(
    branch,
    /verdictKindFor\(\s*resultMode\s*\)/,
    'the disclosure must be chosen by the mode the RESULT was fetched with'
  )
  assert.doesNotMatch(
    branch,
    /[^t]\bmode\s*===\s*'name'/,
    'reading the live `mode` tab here lets a later tab change rewrite a verdict already on screen'
  )

  // And the result's mode must be recorded where the request is made.
  assert.match(
    src,
    /setResultMode\(requestMode\)/,
    'runExplain must record the mode it actually requested'
  )
})

test('an abstain or error row has no round-trip line even when it carries a SMILES', () => {
  // No name was shipped, so there is nothing a round trip could confirm.
  for (const status of ['abstain', 'error']) {
    assert.equal(roundtripLine({ status, roundtrip_smiles: 'CCO', roundtrip_match: true }), null, status)
  }
})

test('a best_effort row that did round-trip shows its proof', () => {
  // The silent-when-absent rule is for a missing proof; a present one is
  // always shown, whatever the tier.
  const line = roundtripLine({ status: 'best_effort', roundtrip_smiles: 'CCO', roundtrip_match: true })
  assert.equal(line.available, true)
  assert.equal(line.smiles, 'CCO')
})

test('a missing proof on a verified tier is worded, not just flagged', () => {
  const line = roundtripLine({ status: 'pin', roundtrip_smiles: null })
  assert.equal(line.lead, 'Round-trip check:')
  assert.equal(line.result, 'unavailable')
  assert.match(line.tail, /not confirmed/)
})

test('Explain.jsx shows the user-supplied disclosure when the verdict is user-supplied', () => {
  // The call is asserted above; inverting the comparison would swap the two
  // disclosures while still calling the right function.
  const src = readFileSync(fileURLToPath(new URL('../pages/Explain.jsx', import.meta.url)), 'utf8')
  assert.match(src, /verdictKindFor\(\s*resultMode\s*\)\s*===\s*'user-supplied'\s*\?/)
})
