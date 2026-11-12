import assert from 'node:assert/strict'
import { test } from 'node:test'

import { watchShareHash } from './useShareLink.js'

function fakeWindow(hash) {
  const win = new EventTarget()
  win.location = { hash }
  return win
}

test('the arrival link is read once', () => {
  const win = fakeWindow('#smiles=CCO')
  const seen = []
  watchShareHash(win, (fields) => seen.push(fields))
  assert.deepEqual(seen, [{ smiles: 'CCO' }])
})

test('a link pasted into a tab already on the route is read too', () => {
  const win = fakeWindow('')
  const seen = []
  watchShareHash(win, (fields) => seen.push(fields))
  assert.deepEqual(seen, [])
  win.location.hash = '#smiles=c1ccccc1'
  win.dispatchEvent(new Event('hashchange'))
  assert.deepEqual(seen, [{ smiles: 'c1ccccc1' }])
})

test('a fragment that is not a share link calls nothing', () => {
  const win = fakeWindow('')
  const seen = []
  watchShareHash(win, (fields) => seen.push(fields))
  win.location.hash = '#main'
  win.dispatchEvent(new Event('hashchange'))
  assert.deepEqual(seen, [])
})

test('unsubscribing stops listening; initial: false skips the arrival read', () => {
  const win = fakeWindow('#smiles=CCO')
  const seen = []
  const stop = watchShareHash(win, (fields) => seen.push(fields), { initial: false })
  assert.deepEqual(seen, [])
  stop()
  win.location.hash = '#smiles=CC'
  win.dispatchEvent(new Event('hashchange'))
  assert.deepEqual(seen, [])
})
