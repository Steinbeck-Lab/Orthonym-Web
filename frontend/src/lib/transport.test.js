import { strict as assert } from 'node:assert'
import { test } from 'node:test'

import { httpError, transportMessage } from './transport.js'

test('httpError keeps the status and the backend detail', async () => {
  const res = new Response(JSON.stringify({ detail: 'Input exceeds the 10-molecule limit' }), { status: 413 })
  const err = await httpError(res, 'POST /api/translate')
  assert.equal(err.status, 413)
  assert.equal(err.message, 'Input exceeds the 10-molecule limit')
})

test('httpError falls back to the status when the body is not JSON', async () => {
  const err = await httpError(new Response('<html>bad gateway</html>', { status: 502 }), 'GET /api/explain')
  assert.equal(err.status, 502)
  assert.equal(err.message, 'GET /api/explain failed with 502')
})

test('a busy or degraded backend is never reported as unreachable', () => {
  // The old text for all of these was "Could not reach Orthonym's backend".
  for (const status of [429, 503, 504, 413, 500]) {
    const text = transportMessage({ status, message: 'x' })
    assert.ok(text && !/could not reach/i.test(text), `${status}: ${text}`)
  }
  assert.match(transportMessage({ status: 503 }), /no worker has a live JVM/)
  assert.match(transportMessage({ status: 429 }), /request limit/)
})

test('a backend that did not answer is left to the unreachable text', () => {
  assert.equal(transportMessage(new TypeError('Failed to fetch')), null)
  assert.equal(transportMessage(null), null)
  // The proxy's answer for a backend that is down (Vite and nginx both).
  assert.equal(transportMessage({ status: 502, message: 'x' }), null)
})

test('a timeout and an oversize input each say their own thing', () => {
  // Both used to fall through to the generic "answered with an error" line,
  // which names neither the wait nor the size.
  assert.equal(
    transportMessage({ status: 504, message: 'x' }),
    'This took too long rather than failed. Try again in a moment.',
  )
  assert.equal(
    transportMessage({ status: 413, message: 'Input exceeds the 10-molecule limit' }),
    'Orthonym refused this input as too large (Input exceeds the 10-molecule limit).',
  )
  assert.match(transportMessage({ status: 500, message: 'x' }), /answered with an error \(500\)/)
})

test('httpError ignores a detail that is not a string', async () => {
  // FastAPI's 422 carries `detail` as a list of objects; as a message it
  // would print "[object Object]".
  const res = new Response(JSON.stringify({ detail: [{ msg: 'field required' }] }), { status: 422 })
  const err = await httpError(res, 'POST /api/translate')
  assert.equal(err.message, 'POST /api/translate failed with 422')
})
