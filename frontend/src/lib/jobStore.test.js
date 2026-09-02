import { strict as assert } from 'node:assert'
import { test } from 'node:test'

import {
  JOB_STORAGE_KEY,
  MAX_REMEMBERED,
  UNKNOWN_EXPIRY_MAX_AGE_SECONDS,
  pruneExpired,
  readJobs,
  rememberJob,
  withJob,
} from './jobStore.js'

// Mostly the pure halves: readJobs/rememberJob/forgetJob touch
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

test('pruneExpired ages out an entry whose expiry never arrived', () => {
  // `expiresAt` is filled in by the first successful status poll. If that
  // poll never lands -- the backend was unreachable, the tab was closed --
  // the entry has no expiry to check, and without this bound it stayed in
  // the browser forever, restoring a panel for a job the server deleted a
  // day ago. rememberedAt is what dates it.
  const now = 1_000_000
  const stale = { jobId: 'orphan', expiresAt: null, rememberedAt: now - UNKNOWN_EXPIRY_MAX_AGE_SECONDS - 1 }
  const recent = { jobId: 'fresh', expiresAt: null, rememberedAt: now - 60 }
  assert.deepEqual(pruneExpired([stale, recent], now), [recent])
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

// ...with one exception, at the bottom: the rule that a TERMINAL job is never
// persisted is this module's headline fix, and it cannot be checked without a
// store to write into. The stub is nine lines and covers exactly the four
// methods jobStore calls.
function stubStorage() {
  const map = new Map()
  globalThis.window = {
    localStorage: {
      getItem: (k) => (map.has(k) ? map.get(k) : null),
      setItem: (k, v) => map.set(k, String(v)),
      removeItem: (k) => map.delete(k),
    },
  }
  return map
}

test('rememberJob refuses a terminal job, and drops one it already held', () => {
  // Both directions matter. The bug this prevents is a FINISHED batch coming
  // back on every reload -- and a guard that only refused NEW terminal writes
  // while leaving an existing entry in place would not have fixed it.
  stubStorage()
  rememberJob({ jobId: 'j1', ownerToken: 't1', moleculeCount: 12, status: 'running' })
  assert.equal(readJobs().length, 1, 'a running job is worth remembering')

  for (const status of ['done', 'failed', 'cancelled']) {
    rememberJob({ jobId: 'j1', ownerToken: 't1', moleculeCount: 12, status })
    assert.deepEqual(readJobs(), [], `status ${status} must not stay in the store`)
    rememberJob({ jobId: 'j1', ownerToken: 't1', moleculeCount: 12, status: 'running' })
  }
})

test('rememberJob still keeps the jobs that might need stopping', () => {
  // The other direction: a guard that refused everything would silently lose
  // the owner token of a 10,000-molecule job, which is the one thing this
  // module exists to hold on to.
  const map = stubStorage()
  for (const status of ['queued', 'running', null, undefined]) {
    map.clear()
    rememberJob({ jobId: 'j2', ownerToken: 'tok', moleculeCount: 9000, status })
    const [entry] = readJobs()
    assert.equal(entry?.jobId, 'j2', `status ${status} must be remembered`)
    assert.equal(entry?.ownerToken, 'tok')
  }
  assert.ok(map.has(JOB_STORAGE_KEY), 'written under the current key')
})
