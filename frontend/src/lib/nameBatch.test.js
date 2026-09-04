import { strict as assert } from 'node:assert'
import { test } from 'node:test'

import { MAX_NAMES, convertNames, parseNameLines } from './nameBatch.js'

const deferred = () => {
  let resolve
  let reject
  const promise = new Promise((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

test('parseNameLines caps at MAX_NAMES and reports the true total', () => {
  const pasted = Array.from({ length: MAX_NAMES + 5 }, (_, i) => `name ${i}`).join('\n')
  const { names, total, truncated } = parseNameLines(pasted)
  assert.equal(names.length, MAX_NAMES)
  assert.equal(total, MAX_NAMES + 5)
  assert.equal(truncated, true)
})

test('convertNames returns rows in INPUT order even when responses settle out of order', async () => {
  // The whole point of the pool. A naive implementation that pushes results
  // as they arrive renumbers the user's list, so row 3 in the table is not
  // line 3 in their paste -- and every InChIKey is then attached to the
  // wrong name.
  const gates = { a: deferred(), b: deferred(), c: deferred() }
  const fetchOne = (name) => gates[name].promise

  const pending = convertNames(['a', 'b', 'c'], { fetchOne, concurrency: 3 })
  gates.c.resolve({ smiles: 'C' })
  gates.a.resolve({ smiles: 'A' })
  gates.b.resolve({ smiles: 'B' })

  const rows = await pending
  assert.deepEqual(rows.map((r) => r.name), ['a', 'b', 'c'])
  assert.deepEqual(rows.map((r) => r.data.smiles), ['A', 'B', 'C'])
  assert.deepEqual(rows.map((r) => r.index), [0, 1, 2])
})

test('one failing name does not abort the batch', async () => {
  // A typo on line 2 says nothing about line 3. A partial answer to 25 names
  // is far more useful than nothing, so a rejection becomes one failed row.
  const fetchOne = (name) =>
    name === 'bad' ? Promise.reject(new Error('boom')) : Promise.resolve({ smiles: 'X' })

  const rows = await convertNames(['good', 'bad', 'alsogood'], { fetchOne, concurrency: 2 })
  assert.deepEqual(rows.map((r) => r.ok), [true, false, true])
  assert.equal(rows[1].error, 'boom')
  assert.equal(rows[1].data, null)
  assert.equal(rows[2].data.smiles, 'X')
})

test('an API error field becomes a failed row, not a successful empty one', async () => {
  // The endpoint answers 200 with { error: "..." } when OPSIN declines. That
  // is a failure for the user even though the HTTP call succeeded.
  const fetchOne = () => Promise.resolve({ smiles: null, error: 'Could not parse this name via OPSIN' })
  const rows = await convertNames(['zzz'], { fetchOne })
  assert.equal(rows[0].ok, false)
  assert.equal(rows[0].error, 'Could not parse this name via OPSIN')
})

test('convertNames never runs more than `concurrency` fetches at once', async () => {
  let inFlight = 0
  let peak = 0
  const fetchOne = async () => {
    inFlight += 1
    peak = Math.max(peak, inFlight)
    await new Promise((r) => setTimeout(r, 1))
    inFlight -= 1
    return { smiles: 'X' }
  }

  await convertNames(Array.from({ length: 12 }, (_, i) => `n${i}`), {
    fetchOne,
    concurrency: 4,
  })
  assert.equal(peak, 4)
})

test('onProgress counts every settled name and reaches the total', async () => {
  const seen = []
  const fetchOne = (name) =>
    name === 'bad' ? Promise.reject(new Error('boom')) : Promise.resolve({ smiles: 'X' })

  await convertNames(['a', 'bad', 'c'], {
    fetchOne,
    concurrency: 2,
    onProgress: (done, total) => seen.push([done, total]),
  })
  // A failure still advances the bar; otherwise a batch with one bad name
  // stalls at 2 of 3 forever.
  assert.deepEqual(seen.at(-1), [3, 3])
  assert.equal(seen.length, 3)
})

test('convertNames on an empty list resolves to an empty array', async () => {
  const rows = await convertNames([], { fetchOne: () => Promise.reject(new Error('never')) })
  assert.deepEqual(rows, [])
})
