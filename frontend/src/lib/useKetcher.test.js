import assert from 'node:assert/strict'
import { test } from 'node:test'

import { isEditorInit } from './useKetcher.js'

test("only our own frame, from our origin, can declare the editor ready", () => {
  const frame = {}
  const origin = 'https://orthonym.example'
  const init = { eventType: 'init' }
  assert.equal(isEditorInit({ source: frame, origin, data: init }, frame, origin), true)
  assert.equal(isEditorInit({ source: {}, origin, data: init }, frame, origin), false)
  assert.equal(isEditorInit({ source: frame, origin: 'https://evil.example', data: init }, frame, origin), false)
  assert.equal(isEditorInit({ source: frame, origin, data: { eventType: 'other' } }, frame, origin), false)
  // No frame mounted yet: nothing is ours.
  assert.equal(isEditorInit({ source: undefined, origin, data: init }, undefined, origin), false)
})
