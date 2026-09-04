/**
 * Build the two downloadable files from rows the page already holds. No
 * endpoint is involved: everything these need has already been fetched.
 */

const CSV_COLUMNS = ['#', 'name', 'smiles', 'canonical_smiles', 'inchi', 'inchikey', 'error']

/**
 * RFC 4180 quoting, and it is load-bearing rather than defensive: IUPAC names
 * contain commas as a matter of course (2,3-dimethylbutane) and so does every
 * InChI. An unquoted writer shifts every column after the first comma, which
 * silently attaches each molecule's InChIKey to the wrong row in a spreadsheet.
 */
function csvField(value) {
  const text = value == null ? '' : String(value)
  return `"${text.replace(/"/g, '""')}"`
}

export function rowsToCsv(rows) {
  const lines = [CSV_COLUMNS.map(csvField).join(',')]
  for (const row of rows) {
    const d = row.data || {}
    lines.push(
      [
        row.index + 1,
        row.name,
        d.smiles,
        d.canonical_smiles,
        d.inchi,
        d.inchikey,
        row.error,
      ]
        .map(csvField)
        .join(',')
    )
  }
  // CRLF per RFC 4180; Excel and every other reader accept it.
  return `${lines.join('\r\n')}\r\n`
}

/**
 * Concatenate each row's molblock into one SDF, tagging each record with the
 * name that produced it and its identifiers.
 *
 * Rows with no molblock are SKIPPED rather than written as an empty record,
 * and the counts come back so the caller can say "wrote 4 of 5". A file that
 * silently loses a molecule is worse than one that is honestly short.
 */
export function rowsToSdf(rows) {
  const records = []
  let skipped = 0

  for (const row of rows) {
    const molblock = row.data?.molblock
    if (!molblock) {
      skipped += 1
      continue
    }
    const fields = [
      ['NAME', row.name],
      ['SMILES', row.data.smiles],
      ['CANONICAL_SMILES', row.data.canonical_smiles],
      ['INCHI', row.data.inchi],
      ['INCHIKEY', row.data.inchikey],
    ]
      .filter(([, value]) => value)
      .map(([tag, value]) => `>  <${tag}>\n${value}\n`)
      .join('\n')

    records.push(`${molblock.replace(/\n*$/, '\n')}${fields}\n$$$$\n`)
  }

  return { text: records.join(''), written: records.length, skipped }
}

/**
 * Hand the browser a file. A Blob plus a synthetic <a download> click is the
 * whole mechanism -- no dependency, and the object URL is revoked immediately
 * afterwards so the blob is not held for the life of the page.
 */
export function downloadText(filename, text, mime) {
  const url = URL.createObjectURL(new Blob([text], { type: mime }))
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}
