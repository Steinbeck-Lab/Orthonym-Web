// The words for a name-check verdict live on the server: every answer and
// every batch row carries `verdict_text`. This file holds only the line that
// says what the check actually did.

/** The one line under a verdict saying what was actually done: true for
 *  every verdict, including the two where no comparison ran. */
export function verdictHow(result) {
  if (result.verdict === 'unreadable') {
    return 'OPSIN could not read this name, so there is no structure to compare.'
  }
  if (result.verdict === 'uncomparable') {
    const side = result.input_inchikey ? 'the structure it describes' : 'your structure'
    return `OPSIN read your name, but no InChIKey could be made for ${side}, so the two could not be compared.`
  }
  // Standard InChI merges tautomers (2-pyridone and pyridin-2-ol share a
  // key), so "Same structure" means the same up to tautomerism: say so.
  return 'OPSIN read your name; the two structures were compared by InChIKey, which counts tautomers as one structure.'
}
