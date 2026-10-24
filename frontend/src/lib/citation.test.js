import assert from 'node:assert/strict'
import { test } from 'node:test'
import { bibtex, citationEntries, referenceAuthors } from './citation.js'

const LIVE = { version: '1.0.9', commit: '81ba930abcdef' }

test('BibTeX cites the paper, then the software at the running version', () => {
  const text = bibtex(LIVE)
  assert.match(text, /@article\{rajan2026orthonym,/)
  assert.match(text, /doi = \{10\.26434\/chemrxiv\.15009769\/v1\}/)
  assert.match(text, /@software\{orthonym,/)
  assert.match(text, /doi = \{10\.5281\/zenodo\.23044199\}/)
  assert.match(text, /version = \{1\.0\.9\}/)
  assert.ok(text.indexOf('@article') < text.indexOf('@software'))
})

test('the note pins the commit and does not repeat the version', () => {
  assert.match(bibtex(LIVE), /note = \{Commit 81ba930\}/)
  assert.equal(bibtex(LIVE).match(/1\.0\.9/g).length, 1)
})

test('no commit, no commit text and no undefined', () => {
  const text = bibtex({ version: '1.0.9', commit: null })
  assert.doesNotMatch(text, /commit|note/i)
  assert.doesNotMatch(text, /undefined|null/)
})

test('before health loads, the software entry has no version', () => {
  const text = bibtex({ version: null, commit: null })
  assert.doesNotMatch(text, /version =/)
  assert.doesNotMatch(text, /undefined|null/)
})

test('authors in CITATION.cff order', () => {
  assert.match(bibtex(LIVE), /author = \{Rajan, Kohulan and Zielesny, Achim and Steinbeck, Christoph\}/)
  assert.equal(referenceAuthors(), 'Rajan, K.; Zielesny, A.; Steinbeck, C.')
})

test('the entries are the data the BibTeX text is written from', () => {
  const [paper, software] = citationEntries(LIVE)
  assert.equal(paper.type, 'article')
  assert.equal(paper.key, 'rajan2026orthonym')
  assert.deepEqual(paper.fields.find(([n]) => n === 'doi'), ['doi', '10.26434/chemrxiv.15009769/v1'])
  assert.equal(software.fields.find(([n]) => n === 'version')[1], '1.0.9')
  // A field with no value is left out, not written empty.
  assert.equal(citationEntries({}).at(1).fields.some(([n]) => n === 'version' || n === 'note'), false)
})
