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
