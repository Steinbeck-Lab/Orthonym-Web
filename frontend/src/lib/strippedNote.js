// The note on a row named after salt stripping (backend app/salts.py). A
// stripped row must never look as if the original was named, so wherever
// the name shows, this sentence shows with it.
export function strippedNote(row) {
  if (row?.strip_skipped) {
    // The switch was on but RDKit could not read the structure (a CDK-only
    // input), so nothing was stripped: never let the switch look applied.
    return 'Salts not stripped: this structure could not be split into fragments, so all of it was named.'
  }
  return row?.stripped_from && row.removed ? `Named after removing: ${row.removed}` : null
}
