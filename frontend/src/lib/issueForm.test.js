import assert from 'node:assert/strict'
import test from 'node:test'

import { prefilledIssueUrl } from './github.js'
import { KINDS, buildIssue, isComplete } from './issueForm.js'

const kindById = (id) => KINDS.find((k) => k.id === id)

const REPO = 'https://github.com/Steinbeck-Lab/Orthonym-Web'
const ENGINE = { page: '/explain', engineVersion: '1.0.7', engineCommit: '61026e217e5d97191ee9fc020fedd7b453d5eb06' }

test('a wrong-name report carries the SMILES, both names and the engine', () => {
  const issue = buildIssue(kindById('wrong-name'), {
    smiles: 'CCO',
    given: 'ethan-1-ol',
    expected: 'ethanol',
    notes: '  ',
  }, ENGINE)
  assert.equal(issue.title, 'Wrong name: CCO')
  assert.equal(issue.labels, 'bug')
  assert.ok(issue.body.includes('**SMILES**\n\n```\nCCO\n```'))
  assert.ok(issue.body.includes('**Name you expected**\n\nethanol'))
  assert.ok(issue.body.includes('- Page: /explain'))
  assert.ok(issue.body.includes('- Engine: v1.0.7 (61026e2)'))
  assert.ok(!issue.body.includes('Anything else'), 'a blank answer leaves no empty section')
})

test('an idea says nothing about the engine and is labelled an enhancement', () => {
  const issue = buildIssue(kindById('idea'), { summary: 'Export SDF\nwith names' }, ENGINE)
  assert.equal(issue.title, 'Idea: Export SDF')
  assert.equal(issue.labels, 'enhancement')
  assert.ok(!issue.body.includes('Engine'))
})

test('each kind is complete only once its one required answer is in', () => {
  assert.equal(isComplete(kindById('site'), { did: 'clicked' }), false)
  assert.equal(isComplete(kindById('site'), { happened: 'nothing' }), true)
  assert.equal(isComplete(kindById('cannot-name'), { smiles: '   ' }), false)
})

test('the link prefills title, body and label, and refuses to grow past a URL', () => {
  const issue = buildIssue(kindById('cannot-name'), { smiles: 'C[NH3+].[Cl-]' }, ENGINE)
  const url = new URL(prefilledIssueUrl(REPO, issue))
  assert.equal(url.origin + url.pathname, `${REPO}/issues/new`)
  assert.equal(url.searchParams.get('title'), 'Could not name: C[NH3+].[Cl-]')
  assert.equal(url.searchParams.get('labels'), 'bug')
  assert.equal(prefilledIssueUrl(REPO, { ...issue, body: 'x'.repeat(9000) }), null)
  assert.equal(prefilledIssueUrl(null, issue), null)
})
