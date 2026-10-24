// The note on a row named after salt stripping (backend app/salts.py). A
// stripped row must never look as if the original was named, so wherever
// the name shows, this sentence shows with it.
export function strippedNote(row) {
  return row?.stripped_from && row.removed ? `Named after removing: ${row.removed}` : null
}
