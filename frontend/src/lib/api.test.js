// The /api/explain contract the page relies on (spec 8.5): the exact key set
// of a response and of each node, on real responses, through the real fetch wrappers.
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { afterEach, test } from 'node:test'

import { explainMolecule, explainName } from './api.js'

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
