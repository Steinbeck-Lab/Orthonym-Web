import assert from 'node:assert/strict'
import { test } from 'node:test'

import { TranslateJobQueuedError } from './api.js'
import { fetchTier, tierNote, TIER_LOADING } from './tierFetch.js'

test('a failed tier fetch is a stated failure, not a missing row', async () => {
  const err = Object.assign(new Error('Orthonym is busy'), { status: 503 })
  const state = await fetchTier('CCO', {}, { translate: async () => { throw err } })
  assert.equal(state.status, 'failed')
  assert.match(tierNote(state), /^Confidence tier unavailable: .*no worker has a live JVM/)
  assert.equal(tierNote(TIER_LOADING), 'Checking the confidence tier…')
})

test('a queued tier fetch cancels its job with the owner token', async () => {
  const cancelled = []
  const state = await fetchTier('CCO', {}, {
    translate: async () => { throw new TranslateJobQueuedError('job9', 1, 'tok9') },
    cancel: async (...args) => { cancelled.push(args) },
  })
  await new Promise((resolve) => setTimeout(resolve, 0))
  assert.deepEqual(cancelled, [['job9', 'tok9']])
  assert.equal(state.status, 'failed')
  assert.match(tierNote(state), /queued/)
})

test('a row is ready and needs no note', async () => {
  const row = { status: 'pin', name: 'ethanol' }
  const state = await fetchTier('CCO', {}, { translate: async () => [row] })
  assert.deepEqual(state, { status: 'ready', row, reason: null })
  assert.equal(tierNote(state), null)
})
