// How to cite the Orthonym engine, as BibTeX.
//
// Copied from the engine's CITATION.cff (github.com/Steinbeck-Lab/Orthonym,
// read 2026-10-24 at engine 1.0.9): its preferred-citation (the ChemRxiv
// paper) and the software record (the Zenodo concept DOI). Change these only
// from a newer CITATION.cff; never add a field the file does not have. The
// running version and commit come from /api/health, so the software entry
// names the engine this deployment actually runs.

export const AUTHORS = Object.freeze([
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

/** "Rajan, K.; Zielesny, A.; Steinbeck, C." for the printed reference. */
export function referenceAuthors() {
  return AUTHORS.map(([family, given]) => `${family}, ${given[0]}.`).join('; ')
}

/** The paper, then the software at `{version, commit}`, as data:
 *  [{type, key, fields: [[name, value], ...]}], empty fields left out. The
 *  BibTeX text and the page both render from this. */
export function citationEntries(engine = {}) {
  const author = AUTHORS.map(([family, given]) => `${family}, ${given}`).join(' and ')
  const entry = (type, key, fields) => ({ type, key, fields: fields.filter(([, value]) => value != null) })
  return [
    entry('article', 'rajan2026orthonym', [
      ['author', author],
      ['title', PAPER.title],
      ['journal', PAPER.journal],
      ['year', PAPER.year],
      ['month', PAPER.month],
      ['doi', PAPER.doi],
      ['url', PAPER.url],
    ]),
    // The version has its own field; the note carries only the commit, since
    // two builds of one version can differ (the engine tracks main).
    entry('software', 'orthonym', [
      ['author', author],
      ['title', SOFTWARE.title],
      ['version', engine.version || null],
      ['doi', SOFTWARE.doi],
      ['url', SOFTWARE.url],
      ['license', SOFTWARE.license],
      ['note', engine.commit ? `Commit ${engine.commit.slice(0, 7)}` : null],
    ]),
  ]
}

/** The same entries as BibTeX text, for the copy button. */
export function bibtex(engine = {}) {
  return citationEntries(engine)
    .map(({ type, key, fields }) => {
      const body = fields.map(([name, value]) => `  ${name} = {${value}}`).join(',\n')
      return `@${type}{${key},\n${body}\n}`
    })
    .join('\n\n')
}
