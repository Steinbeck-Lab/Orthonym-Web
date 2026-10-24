// The name-check verdict words, keyed as backend/app/name_check.py keys them.
// A batch row carries only the key; the single check carries the words too.
// About STRUCTURE only: never "correct", which would claim the name is the
// preferred IUPAC name.
export const VERDICT_TEXT = Object.freeze({
  same: 'Same structure',
  protonation: 'Same skeleton; protonation differs',
  stereo: 'Same skeleton; stereo or isotopes differ',
  different: 'Different structure',
  unreadable: 'OPSIN cannot read this name',
  uncomparable: 'Could not compare',
})

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
  return 'OPSIN read your name; the two structures were compared by InChIKey.'
}
