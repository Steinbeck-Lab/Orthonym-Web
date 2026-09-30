import { strict as assert } from 'node:assert'
import { test } from 'node:test'

import {
  PAGE_SIZE,
  clampPage,
  expiryLabel,
  isTerminal,
  needsJob,
  pageCount,
  progressPercent,
  stateLabel,
} from './batchJob.js'

test('pageCount counts pages against retrievable rows, not a fixed guess', () => {
  assert.equal(pageCount(0), 0)
  assert.equal(pageCount(1), 1)
  assert.equal(pageCount(PAGE_SIZE), 1)
  // The row that spills over has to get a page of its own.
  assert.equal(pageCount(PAGE_SIZE + 1), 2)
  assert.equal(pageCount(10000, 50), 200)
})

test('pageCount treats a missing or nonsense count as no pages', () => {
  // A job whose meta was evicted answers with nothing useful; offering
  // page 1 of NaN would render a table of undefined rows.
  assert.equal(pageCount(undefined), 0)
  assert.equal(pageCount(-5), 0)
  assert.equal(pageCount(Number.NaN), 0)
})

test('clampPage never offers a page the job cannot answer', () => {
  // 120 rows at 50 a page is three pages: 0, 1, 2.
  assert.equal(clampPage(2, 120), 2)
  assert.equal(clampPage(3, 120), 2, 'past the last page must clamp to the last page')
  assert.equal(clampPage(99, 120), 2)
  assert.equal(clampPage(-1, 120), 0)
  assert.equal(clampPage(1, 0), 0, 'no rows means there is only page 0 to be on')
})

test('progressPercent counts failures as done, because the server does', () => {
  // JobStatusResponse.failed is a SUBSET of done. Adding them would put a job
  // with any failures past 100%.
  assert.equal(progressPercent({ done: 50, failed: 10, total: 100 }), 50)
  assert.equal(progressPercent({ done: 100, failed: 100, total: 100 }), 100)
  assert.equal(progressPercent({ done: 0, total: 100 }), 0)
})

test('progressPercent survives a job that reports no total', () => {
  assert.equal(progressPercent({ done: 5, total: 0 }), 0)
  assert.equal(progressPercent({}), 0)
  assert.equal(progressPercent(), 0)
})

test('a locally-remembered cancel softens "failed", and nothing else', () => {
  // The backend accepts a race where _close_job writes "failed" over
  // "cancelled" (redis_store.py). Someone who pressed Stop must not be told
  // their data broke.
  assert.equal(stateLabel('failed', { cancelRequested: true }), 'Stopped')
  assert.equal(stateLabel('cancelled', { cancelRequested: true }), 'Stopped')
  // ...but it must never turn a real failure into a stop when nobody asked,
  assert.equal(stateLabel('failed'), 'Failed')
  // nor claim a job was stopped when it actually finished.
  assert.equal(stateLabel('done', { cancelRequested: true }), 'Finished')
  assert.equal(stateLabel('running'), 'Running')
  assert.equal(stateLabel('queued'), 'Queued')
})

test('isTerminal knows exactly which states stop the polling', () => {
  assert.equal(isTerminal('done'), true)
  assert.equal(isTerminal('failed'), true)
  assert.equal(isTerminal('cancelled'), true)
  // Poll these two or the progress bar never moves.
  assert.equal(isTerminal('queued'), false)
  assert.equal(isTerminal('running'), false)
})

test('expiryLabel says when results go, and admits when they are gone', () => {
  const now = 1_000_000
  assert.equal(expiryLabel(now + 23 * 3600, now), 'expires in 23 hours')
  assert.equal(expiryLabel(now + 3600, now), 'expires in 1 hour')
  assert.equal(expiryLabel(now + 90, now), 'expires in 2 minutes')
  assert.equal(expiryLabel(now + 30, now), 'expires in 1 minute', 'never round down to zero')
  assert.equal(expiryLabel(now - 1, now), 'expired')
  assert.equal(expiryLabel(undefined, now), null)
})

test('needsJob draws the line where the server draws it', () => {
  // FAST_PATH_MAX_MOLECULES is 10: ten still answer inline, eleven do not.
  assert.equal(needsJob(10, 10), false)
  assert.equal(needsJob(11, 10), true)
  assert.equal(needsJob(1, 10), false)
  assert.equal(needsJob(Number.NaN, 10), false)
})

test('clampPage survives a non-number, a fraction and a custom page size', () => {
  // NaN would reach the request as "page=NaN"; a fraction as page=1.7; and a
  // caller with its own page size must be clamped against that size.
  assert.equal(clampPage(Number.NaN, 120), 0)
  assert.equal(clampPage(1.7, 120), 1)
  assert.equal(clampPage(5, 120, 10), 5, '120 rows at 10 a page has a page 5')
  assert.equal(clampPage(99, 120, 10), 11)
})

test('progressPercent stays inside 0..100 and rounds to the nearest whole number', () => {
  // A poll racing a status write can report done past total; the bar must not
  // overflow its track or go negative.
  assert.equal(progressPercent({ done: 150, total: 100 }), 100)
  assert.equal(progressPercent({ done: -5, total: 100 }), 0)
  assert.equal(progressPercent({ done: 1, total: 3 }), 33)
  assert.equal(progressPercent({ done: 2, total: 3 }), 67)
  assert.equal(progressPercent({ done: 5, total: Number.NaN }), 0)
})

test('stateLabel words every state on its own', () => {
  assert.equal(stateLabel('cancelled'), 'Stopped')
  assert.equal(stateLabel('a-state-the-server-never-sends'), 'Unknown')
})

test('expiryLabel rounds the way a reader expects at its edges', () => {
  const now = 1_000_000
  assert.equal(expiryLabel(now, now), 'expired', 'no time left is expired, not "0 minutes"')
  assert.equal(expiryLabel(now + 23.5 * 3600, now), 'expires in 23 hours', 'hours round down')
  assert.equal(expiryLabel(now + 70, now), 'expires in 1 minute', 'minutes round to nearest')
  assert.equal(expiryLabel(now + 20, now), 'expires in 1 minute', 'never "0 minutes"')
})
