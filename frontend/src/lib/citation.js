// How to cite the Orthonym engine, as BibTeX and RIS.
//
// Copied from the engine's CITATION.cff (github.com/Steinbeck-Lab/Orthonym,
// read 2026-10-24 at engine 1.0.9): its preferred-citation (the ChemRxiv
// paper) and the software record (the Zenodo DOI). Change these only from a
// newer CITATION.cff; never add a field the file does not have. The running
// version and commit come from /api/health, so the software entry names the
// engine this deployment actually runs.

const AUTHORS = Object.freeze([
  ['Rajan', 'Kohulan'],
  ['Zielesny', 'Achim'],
  ['Steinbeck', 'Christoph'],
])

export const PAPER = Object.freeze({
  title: 'Orthonym: verified IUPAC names for chemical structures in the wild',
  journal: 'ChemRxiv',
  year: 2026,
  month: 10,
  doi: '10.26434/chemrxiv.15009769/v1',
  url: 'https://doi.org/10.26434/chemrxiv.15009769/v1',
})

export const SOFTWARE = Object.freeze({
  title: 'Orthonym',
  doi: '10.5281/zenodo.23044199',
  url: 'https://github.com/Steinbeck-Lab/Orthonym',
  license: 'MIT',
})

function note({ version, commit } = {}) {
  if (!version) return null
  return commit ? `Version ${version}, commit ${commit.slice(0, 7)}` : `Version ${version}`
}

function bibEntry(type, key, fields) {
  const body = fields
    .filter(([, value]) => value != null)
    .map(([name, value]) => `  ${name} = {${value}}`)
    .join(',\n')
  return `@${type}{${key},\n${body}\n}`
}

/** The paper, then the software at `{version, commit}`, as BibTeX. */
export function bibtex(engine = {}) {
  const author = AUTHORS.map(([family, given]) => `${family}, ${given}`).join(' and ')
  return [
    bibEntry('article', 'rajan2026orthonym', [
      ['author', author],
      ['title', PAPER.title],
      ['journal', PAPER.journal],
      ['year', PAPER.year],
      ['month', PAPER.month],
      ['doi', PAPER.doi],
      ['url', PAPER.url],
    ]),
    bibEntry('software', 'orthonym', [
      ['author', author],
      ['title', SOFTWARE.title],
      ['version', engine.version || null],
      ['doi', SOFTWARE.doi],
      ['url', SOFTWARE.url],
      ['license', SOFTWARE.license],
      ['note', note(engine)],
    ]),
  ].join('\n\n')
}

function risRecord(lines) {
  return [...lines.filter(([, value]) => value != null), ['ER', '']]
    .map(([tag, value]) => `${tag}  - ${value}`)
    .join('\n')
}

/** The same two records as RIS. */
export function ris(engine = {}) {
  const au = AUTHORS.map(([family, given]) => ['AU', `${family}, ${given}`])
  return [
    risRecord([
      ['TY', 'JOUR'],
      ...au,
      ['TI', PAPER.title],
      ['JO', PAPER.journal],
      ['PY', PAPER.year],
      ['DO', PAPER.doi],
      ['UR', PAPER.url],
    ]),
    risRecord([
      ['TY', 'COMP'],
      ...au,
      ['TI', SOFTWARE.title],
      ['ET', engine.version || null],
      ['DO', SOFTWARE.doi],
      ['UR', SOFTWARE.url],
      ['N1', note(engine)],
    ]),
  ].join('\n\n') + '\n'
}
