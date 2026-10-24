// The /api/explain contract the page relies on (spec 8.5): the exact key set
// of a response and of each node, on real responses, through the real fetch wrappers.
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { afterEach, test } from 'node:test'

import { checkName, createJob, explainMolecule, explainName, fetchJobResults, jobResultsCsvUrl, jobResultsSdfUrl, translateBatch } from './api.js'

const REAL = JSON.parse(readFileSync(new URL('./explainResponses.fixture.json', import.meta.url), 'utf8'))
const RESPONSE_KEYS = ['atom_points', 'error', 'name', 'nodes', 'smiles', 'svg', 'total_atoms']
const NODE_KEYS = ['atoms_unmapped', 'copies', 'id', 'kind', 'label', 'lights', 'line', 'owns', 'parent', 'span']
const realFetch = globalThis.fetch

afterEach(() => { globalThis.fetch = realFetch })

function stub(body, status = 200) {
  const calls = []
  globalThis.fetch = async (url) => {
    calls.push(url)
    return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })
  }
  return calls
}

test('every stored response has exactly the documented keys, and every node the 10 node keys', () => {
  for (const [key, r] of Object.entries(REAL)) {
    assert.deepEqual(Object.keys(r).sort(), RESPONSE_KEYS, key)
    for (const node of r.nodes) assert.deepEqual(Object.keys(node).sort(), NODE_KEYS, `${key}: ${node.label}`)
  }
})

test('node fields have the documented types', () => {
  for (const r of Object.values(REAL)) {
    for (const n of r.nodes) {
      assert.equal(typeof n.id, 'string')
      assert.ok(n.parent === null || typeof n.parent === 'string')
      assert.equal(typeof n.kind, 'string')
      assert.equal(typeof n.label, 'string')
      assert.ok(n.span === null || (Array.isArray(n.span) && n.span.length === 2 && n.span[0] < n.span[1]))
      assert.equal(typeof n.copies, 'number')
      assert.ok(Array.isArray(n.owns) && Array.isArray(n.lights))
      assert.equal(typeof n.atoms_unmapped, 'boolean')
      assert.equal(typeof n.line, 'string')
    }
  }
})

test('explainName asks /api/explain-name and returns the body untouched', async () => {
  const body = REAL['name:nonsenseane']
  const calls = stub(body)
  assert.deepEqual(await explainName('nonsenseane'), body)
  assert.deepEqual(calls, ['/api/explain-name?name=nonsenseane'])
})

test('explainMolecule encodes the SMILES and returns nodes as sent', async () => {
  const body = REAL['smiles:CC(C)Cc1ccc(cc1)C(C)C(=O)O']
  const calls = stub(body)
  const out = await explainMolecule('CC(C)Cc1ccc(cc1)C(C)C(=O)O')
  assert.deepEqual(calls, [`/api/explain?smiles=${encodeURIComponent('CC(C)Cc1ccc(cc1)C(C)C(=O)O')}`])
  assert.deepEqual(out.nodes, body.nodes)
})

test('a non-2xx answer rejects with status and the backend detail', async () => {
  stub({ detail: 'Explain is busy' }, 503)
  await assert.rejects(explainName('x'), (err) => err.status === 503 && err.message === 'Explain is busy')
})

test('fetchJobResults sends one status param per filtered tier', async () => {
  const calls = stub({ rows: [] })
  await fetchJobResults('job1', { statuses: ['abstain', 'error'] })
  assert.match(calls[0], /status=abstain&status=error/)
})

test('fetchJobResults with no filter sends no status param', async () => {
  const calls = stub({ rows: [] })
  await fetchJobResults('job1', {})
  assert.doesNotMatch(calls[0], /status=/)
})

test('the SDF download sits beside the CSV one', () => {
  assert.equal(jobResultsSdfUrl('abc'), jobResultsCsvUrl('abc').replace(/\.csv$/, '.sdf'))
  assert.equal(jobResultsSdfUrl('a/b'), '/api/jobs/a%2Fb/results.sdf')
})

test('checkName POSTs the pair as JSON, never in the URL', async () => {
  let seen
  globalThis.fetch = async (url, init) => {
    seen = { url, init }
    return new Response(JSON.stringify({ verdict: 'same' }), { status: 200, headers: { 'content-type': 'application/json' } })
  }
  const body = await checkName('CCO', 'ethanol')
  assert.equal(body.verdict, 'same')
  assert.equal(seen.url, '/api/name-check')
  assert.equal(seen.init.method, 'POST')
  assert.deepEqual(JSON.parse(seen.init.body), { smiles: 'CCO', name: 'ethanol' })
})

test('checkName rejects a non-2xx with its status', async () => {
  stub({ detail: 'Could not parse' }, 400)
  await assert.rejects(checkName('C1CC', 'x'), (err) => err.status === 400)
})

test('createJob sends the job kind, name by default', async () => {
  const seen = []
  globalThis.fetch = async (url, init) => {
    seen.push(init)
    return new Response(JSON.stringify({ job_id: 'j' }), { status: 200, headers: { 'content-type': 'application/json' } })
  }
  await createJob({ text: 'CCO' })
  assert.equal(JSON.parse(seen[0].body).kind, 'name')
  await createJob({ file: new Blob(['smiles,name\nCCO,ethanol\n']), kind: 'check' })
  assert.equal(seen[1].body.get('kind'), 'check')
})

test('the strip switch travels on every naming request, off by default', async () => {
  const seen = []
  globalThis.fetch = async (url, init) => {
    seen.push(init)
    const body = url === '/api/translate' ? { results: [] } : { job_id: 'j' }
    return new Response(JSON.stringify(body), { status: 200, headers: { 'content-type': 'application/json' } })
  }
  await translateBatch(['CCO'])
  assert.equal(JSON.parse(seen[0].body).strip_salts, false)
  await translateBatch(['CCO.Cl'], { stripSalts: true })
  assert.equal(JSON.parse(seen[1].body).strip_salts, true)
  await createJob({ file: new Blob(['CCO.Cl\n']), stripSalts: true })
  assert.equal(seen[2].body.get('strip_salts'), 'true')
  await createJob({ text: 'CCO' })
  assert.equal(JSON.parse(seen[3].body).strip_salts, false)
})
