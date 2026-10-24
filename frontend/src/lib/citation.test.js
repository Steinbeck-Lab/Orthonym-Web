import assert from 'node:assert/strict'
import { test } from 'node:test'
import { bibtex, ris } from './citation.js'

const LIVE = { version: '1.0.9', commit: '81ba930abcdef' }

test('BibTeX cites the paper, then the software at the running version', () => {
  const text = bibtex(LIVE)
  assert.match(text, /@article\{rajan2026orthonym,/)
  assert.match(text, /doi = \{10\.26434\/chemrxiv\.15009769\/v1\}/)
  assert.match(text, /@software\{orthonym,/)
  assert.match(text, /doi = \{10\.5281\/zenodo\.23044199\}/)
  assert.match(text, /version = \{1\.0\.9\}/)
  assert.match(text, /commit 81ba930/)
  assert.ok(text.indexOf('@article') < text.indexOf('@software'))
})

test('no commit, no commit text and no undefined', () => {
  const text = bibtex({ version: '1.0.9', commit: null })
  assert.doesNotMatch(text, /commit/)
  assert.doesNotMatch(text, /undefined|null/)
  assert.doesNotMatch(ris({ version: '1.0.9', commit: null }), /commit|undefined|null/)
})

test('before health loads, the software entry has no version', () => {
  const text = bibtex({ version: null, commit: null })
  assert.doesNotMatch(text, /version =/)
  assert.doesNotMatch(text, /undefined|null/)
  assert.doesNotMatch(ris({}), /undefined|null|ET {2}-/)
})

test('RIS has a journal record, then a software record, each closed', () => {
  const text = ris(LIVE)
  assert.match(text, /^TY {2}- JOUR/)
  assert.match(text, /DO {2}- 10\.26434\/chemrxiv\.15009769\/v1/)
  assert.match(text, /TY {2}- COMP/)
  assert.match(text, /ET {2}- 1\.0\.9/)
  assert.equal(text.match(/^TY {2}- /gm).length, 2)
  assert.equal(text.match(/^ER {2}- $/gm).length, 2)
})

test('authors in CITATION.cff order, in both formats', () => {
  assert.match(bibtex(LIVE), /author = \{Rajan, Kohulan and Zielesny, Achim and Steinbeck, Christoph\}/)
  const au = ris(LIVE).match(/^AU {2}- .*$/gm).slice(0, 3)
  assert.deepEqual(au, ['AU  - Rajan, Kohulan', 'AU  - Zielesny, Achim', 'AU  - Steinbeck, Christoph'])
})
