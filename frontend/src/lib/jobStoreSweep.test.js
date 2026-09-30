import { strict as assert } from 'node:assert'
import { test } from 'node:test'

import { JOB_STORAGE_KEY, readJobs } from './jobStore.js'

// The sweep runs once per process, on the first storage access, so it gets a
// file (and so a process) of its own rather than a slot after tests that have
// already spent it.
test('the first read of the store sweeps job lists left by older versions', () => {
  const map = new Map([
    ['orthonym.jobs.v1', '[{"jobId":"dead","ownerToken":"stale"}]'],
    ['theme', 'dark'],
  ])
  const keys = () => [...map.keys()]
  globalThis.window = {
    localStorage: {
      get length() {
        return map.size
      },
      key: (i) => keys()[i] ?? null,
      getItem: (k) => (map.has(k) ? map.get(k) : null),
      setItem: (k, v) => map.set(k, String(v)),
      removeItem: (k) => map.delete(k),
    },
  }
  readJobs()
  assert.equal(map.has('orthonym.jobs.v1'), false, 'a dead owner token must not linger')
  assert.equal(map.get('theme'), 'dark')
  assert.equal(map.has(JOB_STORAGE_KEY), false)
})
