import { strict as assert } from 'node:assert'
import { test } from 'node:test'

import { rowsToCsv, rowsToSdf } from './molExport.js'

const ok = (index, name, data) => ({ index, name, ok: true, data, error: null })
const bad = (index, name, error) => ({ index, name, ok: false, data: null, error })

const ASPIRIN = {
  smiles: 'C(C)(=O)OC1=C(C(=O)O)C=CC=C1',
  canonical_smiles: 'CC(=O)Oc1ccccc1C(=O)O',
  inchi: 'InChI=1S/C9H8O4/c1-6(10)13-8-5-3-2-4-7(8)9(11)12/h2-5H,1H3,(H,11,12)',
  inchikey: 'BSYNRYMUTXBXSQ-UHFFFAOYSA-N',
  molblock: '\n     RDKit          2D\n\n  1  0  0  0  0  0  0  0  0  0999 V2000\nM  END\n',
}

test('rowsToCsv quotes a name containing a comma', () => {
  // IUPAC names contain commas as a matter of course (2,3-dimethylbutane),
  // and so does every InChI. An unquoted writer shifts every later column.
  const csv = rowsToCsv([ok(0, '2,3-dimethylbutane', ASPIRIN)])
  const dataLine = csv.trim().split('\n')[1]
  assert.ok(dataLine.includes('"2,3-dimethylbutane"'))
  // The row still has exactly the 7 columns the header declares.
  assert.equal(csv.trim().split('\n')[0].split(',').length, 7)
})

test('rowsToCsv doubles an embedded double quote', () => {
  const csv = rowsToCsv([ok(0, 'a "quoted" name', ASPIRIN)])
  assert.ok(csv.includes('"a ""quoted"" name"'))
})

test('rowsToCsv keeps failed rows, carrying their error', () => {
  // Dropping them would silently shorten the file and lose the numbering.
  const csv = rowsToCsv([ok(0, 'aspirin', ASPIRIN), bad(1, 'zzz', 'Could not parse')])
  const lines = csv.trim().split('\n')
  assert.equal(lines.length, 3) // header + 2 rows
  assert.ok(lines[2].includes('Could not parse'))
})

test('rowsToCsv writes a missing identifier as an empty field, never "null"', () => {
  const csv = rowsToCsv([ok(0, 'x', { ...ASPIRIN, inchi: null })])
  assert.ok(!csv.includes('null'))
  assert.ok(!csv.includes('undefined'))
})

test('rowsToSdf terminates every record and reports what it wrote', () => {
  const { text, written, skipped } = rowsToSdf([
    ok(0, 'aspirin', ASPIRIN),
    ok(1, 'other', ASPIRIN),
  ])
  assert.equal(written, 2)
  assert.equal(skipped, 0)
  assert.equal(text.match(/\$\$\$\$/g).length, 2)
  assert.ok(text.includes('>  <NAME>'))
  assert.ok(text.includes('aspirin'))
})

test('rowsToSdf skips a row with no molblock and counts it', () => {
  // An empty record would produce a file that silently loses a molecule, so
  // the caller is told the count and can say "wrote 1 of 2".
  const { written, skipped, text } = rowsToSdf([
    ok(0, 'aspirin', ASPIRIN),
    ok(1, 'nocoords', { ...ASPIRIN, molblock: null }),
    bad(2, 'zzz', 'Could not parse'),
  ])
  assert.equal(written, 1)
  assert.equal(skipped, 2)
  assert.equal(text.match(/\$\$\$\$/g).length, 1)
})

test('rowsToSdf on nothing writable returns empty text and writes nothing', () => {
  const { text, written, skipped } = rowsToSdf([bad(0, 'zzz', 'nope')])
  assert.equal(written, 0)
  assert.equal(skipped, 1)
  assert.equal(text, '')
})

test('rowsToCsv writes the exact file: numbering, column order, quoting, CRLF', () => {
  // A spreadsheet reads by position. A swapped pair of columns, a 0-based
  // number or a bare LF each corrupt the file while every row still "looks" right.
  const csv = rowsToCsv([ok(0, 'aspirin', ASPIRIN), bad(1, 'zzz', 'Could not parse')])
  assert.equal(
    csv,
    '"#","name","smiles","canonical_smiles","inchi","inchikey","error"\r\n' +
      `"1","aspirin","${ASPIRIN.smiles}","${ASPIRIN.canonical_smiles}","${ASPIRIN.inchi}","${ASPIRIN.inchikey}",""\r\n` +
      '"2","zzz","","","","","Could not parse"\r\n',
  )
})

test('rowsToSdf writes the exact record: tags, blank lines and terminator', () => {
  // The record is machine-read. A dropped tag, a missing blank line or a
  // "$$$$" without its newline glues the next molblock onto the terminator.
  const first = { ...ASPIRIN, molblock: 'A\nM  END\n\n\n' }
  const second = { ...ASPIRIN, molblock: 'B\nM  END', inchi: null }
  const { text } = rowsToSdf([ok(0, 'aspirin', first), ok(1, 'other', second)])
  const tags = (inchi) =>
    '>  <NAME>\n' + '{n}\n\n' +
    `>  <SMILES>\n${ASPIRIN.smiles}\n\n` +
    `>  <CANONICAL_SMILES>\n${ASPIRIN.canonical_smiles}\n\n` +
    (inchi ? `>  <INCHI>\n${ASPIRIN.inchi}\n\n` : '') +
    `>  <INCHIKEY>\n${ASPIRIN.inchikey}\n\n` +
    '$$$$\n'
  assert.equal(
    text,
    `A\nM  END\n${tags(true).replace('{n}', 'aspirin')}` +
      `B\nM  END\n${tags(false).replace('{n}', 'other')}`,
  )
})
