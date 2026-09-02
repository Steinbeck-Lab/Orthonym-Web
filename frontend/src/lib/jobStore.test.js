import { strict as assert } from 'node:assert'
import { test } from 'node:test'

import { MAX_REMEMBERED, pruneExpired, withJob } from './jobStore.js'

// Only the pure halves are tested here: readJobs/rememberJob/forgetJob touch
// window.localStorage, which node:test has no business pretending to be. The
// rules worth protecting -- what gets dropped, and what order things sit in --
// live in these two functions precisely so they can be checked.

test('pruneExpired drops jobs the server can no longer answer for', () => {
  const now = 1_000_000
  const kept = { jobId: 'live', expiresAt: now + 60 }
  const gone = { jobId: 'dead', expiresAt: now - 1 }
  const result = pruneExpired([kept, gone], now)
  assert.deepEqual(result, [kept])
})

test('pruneExpired keeps a job whose expiry is not known yet', () => {
  // The submission envelope carries no expires_at -- only the first status
  // poll does. Dropping those would throw away the owner token of the job
  // that was just submitted, which is the one the user most needs.
  const now = 1_000_000
  const fresh = { jobId: 'just-submitted', expiresAt: null }
  assert.deepEqual(pruneExpired([fresh], now), [fresh])
})

test('pruneExpired throws out entries that are not usable jobs', () => {
  const now = 1_000_000
  const good = { jobId: 'ok', expiresAt: null }
  const junk = [null, undefined, {}, { jobId: '' }, { jobId: 42 }, 'nope']
  assert.deepEqual(pruneExpired([...junk, good], now), [good])
  assert.deepEqual(pruneExpired('not an array', now), [])
})

test('withJob puts the newest first and never keeps two of one job', () => {
  const older = { jobId: 'a', ownerToken: 'token-a' }
  const other = { jobId: 'b', ownerToken: 'token-b' }
  const replacement = { jobId: 'a', ownerToken: 'token-a2' }

  const result = withJob([older, other], replacement)

  assert.equal(result.length, 2, 'resubmitting the same id must not duplicate it')
  assert.deepEqual(result[0], replacement, 'the newest entry leads')
  // The replacement's token has to win: a stale token cannot cancel anything.
  assert.equal(result[0].ownerToken, 'token-a2')
  assert.deepEqual(result[1], other)
})

test('withJob caps the list, dropping the oldest', () => {
  const many = Array.from({ length: MAX_REMEMBERED }, (_, index) => ({
    jobId: `job-${index}`,
  }))
  const result = withJob(many, { jobId: 'newest' })

  assert.equal(result.length, MAX_REMEMBERED)
  assert.equal(result[0].jobId, 'newest')
  assert.equal(
    result.some((entry) => entry.jobId === `job-${MAX_REMEMBERED - 1}`),
    false,
    'the oldest remembered job is the one that goes'
  )
})
