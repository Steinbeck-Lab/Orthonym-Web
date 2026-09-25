import { strict as assert } from 'node:assert'
import { test } from 'node:test'

import { GITHUB_URL, isReportable, reportIssueUrl, resolveGithubUrl } from './github.js'

const REPO = 'https://github.com/Steinbeck-Lab/Orthonym-Web'

function query(url) {
  return new URL(url).searchParams
}

test('the repo build arg: unset and EMPTY both mean the default; none means off', () => {
  // Compose passes an unset VITE_GITHUB_URL as '' (docker-compose.yml), so ''
  // is the case that matters; `??` instead of `||` would ship no link at all.
  assert.equal(resolveGithubUrl(''), REPO)
  assert.equal(resolveGithubUrl(undefined), REPO)
  assert.equal(resolveGithubUrl('none'), null)
  assert.equal(resolveGithubUrl('https://github.com/fork/x'), 'https://github.com/fork/x')
  // node --test has no import.meta.env at all.
  assert.equal(GITHUB_URL, REPO)
})

test('an abstain and an engine failure are reportable; a bad SMILES is not', () => {
  assert.equal(isReportable({ smiles: 'O=[U](=O)=O', status: 'abstain', limit_code: 'UNSUPPORTED_ELEMENT' }), true)
  assert.equal(isReportable({ smiles: 'CCO', status: 'error', limit_code: 'engine_error' }), true)
  assert.equal(isReportable({ smiles: 'CCO', status: 'error', limit_code: 'timeout' }), true)
  // The visitor's typo: no limit_code. Reporting it would file noise.
  assert.equal(isReportable({ smiles: 'C1CC', status: 'error', limit_code: null, error: 'Could not parse this SMILES string' }), false)
  // A name was shipped: not "could not name".
  for (const status of ['pin', 'fallback', 'best_effort']) {
    assert.equal(isReportable({ smiles: 'CCO', status }), false, status)
  }
  // The visitor's own switches withheld a name the engine found.
  assert.equal(isReportable({ smiles: 'CCO', status: 'abstain', limit_code: 'unverified_withheld' }), false)
  // Nothing to put in the issue -- also every never-attempted timeout row.
  assert.equal(isReportable({ smiles: null, status: 'abstain' }), false)
  assert.equal(isReportable({ smiles: null, status: 'error', limit_code: 'timeout' }), false)
  assert.equal(isReportable(null), false)
})

test('the issue carries the SMILES and what the engine said, exactly', () => {
  const smiles = 'C[NH3+].[Cl-]'
  const url = reportIssueUrl(REPO, {
    smiles,
    status: 'abstain',
    limit_code: 'UNNAMEABLE',
    formula: 'CH6ClN',
    error: null,
    input: 'C[NH3+].[Cl-] SECRET-ID-42',
    input_id: 'SECRET-ID-42',
  }, 'Home')
  assert.ok(url.startsWith(`${REPO}/issues/new?`))
  const q = query(url)
  // `+` in a SMILES must survive the query string, not turn into a space.
  assert.ok(q.get('body').includes('```\nC[NH3+].[Cl-]\n```'))
  assert.ok(q.get('body').includes('- Reason code: `UNNAMEABLE`'))
  assert.ok(q.get('body').includes('- Formula: CH6ClN'))
  assert.ok(q.get('body').includes('- Page: Home'))
  assert.equal(q.get('title'), `Could not name: ${smiles}`)
  assert.equal(q.get('labels'), 'bug')
  // The visitor's own compound label never leaves the page.
  assert.ok(!url.includes('SECRET'))
})

test('a crash report says the engine failed and carries its message', () => {
  const q = query(reportIssueUrl(REPO, {
    smiles: 'CCN',
    status: 'error',
    limit_code: 'engine_error',
    formula: null,
    error: 'Naming failed: boom',
  }, 'Explain'))
  const body = q.get('body')
  assert.ok(body.includes('- Result: the engine failed'))
  assert.ok(body.includes('- Reason code: `engine_error`'))
  assert.ok(body.includes('- Message: Naming failed: boom'))
  assert.ok(!body.includes('Formula'), 'a null formula must not print an empty line')
})

test('the issue states the switches the result was named with, and only when known', () => {
  const row = { smiles: 'CCO', status: 'abstain', limit_code: 'UNNAMEABLE' }
  const strict = query(reportIssueUrl(REPO, row, 'Home', { bestEffort: false, verify: true })).get('body')
  assert.ok(strict.includes('- Best-effort mode: off'))
  assert.ok(strict.includes('- OPSIN verify: on'))
  // A batch job from before the backend recorded them: say nothing, not "on".
  for (const settings of [undefined, null, { bestEffort: null, verify: undefined }]) {
    const body = query(reportIssueUrl(REPO, row, 'Home (batch)', settings)).get('body')
    assert.ok(!body.includes('Best-effort'), JSON.stringify(settings))
    assert.ok(!body.includes('OPSIN verify'), JSON.stringify(settings))
  }
})

test('no repository, or one not on github.com, gets no link', () => {
  const row = { smiles: 'CCO', status: 'abstain' }
  assert.equal(reportIssueUrl(null, row, 'Home'), null)
  assert.equal(reportIssueUrl('https://gitlab.com/x/y', row, 'Home'), null)
  assert.equal(reportIssueUrl(REPO, { smiles: 'CCO', status: 'pin' }, 'Home'), null)
})

test('the longest SMILES the backend accepts still fits a github.com URL', () => {
  // inputs.py caps a SMILES at 2000 characters. Brackets and `=` all
  // percent-encode, so this is close to the worst case; GitHub refuses
  // addresses much past 8 KB.
  const smiles = '[C@@H]=('.repeat(250)
  assert.equal(smiles.length, 2000)
  const url = reportIssueUrl(REPO, {
    smiles,
    status: 'error',
    limit_code: 'engine_error',
    error: 'Naming failed: something long enough to matter here',
  }, 'Home (batch)')
  assert.ok(url, 'the longest typed SMILES must still get a link')
  assert.ok(url.length < 8000, `URL is ${url.length} characters`)
  assert.equal(query(url).get('title').length, 'Could not name: '.length + 61)
})

test('an SDF structure too big for a github.com address gets no link, not a broken one', () => {
  // SDF records skip the 2000-character cap (inputs.py _from_mol); a
  // 200-residue peptide measured 3965 characters.
  const smiles = '[C@@H]=('.repeat(500)
  assert.equal(reportIssueUrl(REPO, { smiles, status: 'abstain' }, 'Home (batch)'), null)
})
