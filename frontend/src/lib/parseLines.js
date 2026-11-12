/**
 * Split pasted text into trimmed, non-blank lines, capped at `max`.
 *
 * `total` is the count BEFORE the cap, deliberately: the UI tells the user
 * how many lines they pasted and how many will be processed, and reporting
 * the capped number instead would hide the drop.
 */
// Exactly the boundaries Python's str.splitlines() breaks on, which is how the
// backend splits the same text. Splitting on \n alone let a share link joined
// by \r count as ONE line here (so it auto-named on the fast path) while the
// backend expanded it to many, past the inline cap, with all but one result
// never shown.
// eslint-disable-next-line no-control-regex -- \x1c-\x1e are line breaks to Python
const LINE_BREAK = /\r\n|[\n\r\v\f\u001c-\u001e\u0085\u2028\u2029]/

export function splitLines(rawText, max) {
  const lines = String(rawText ?? '')
    .split(LINE_BREAK)
    .map((line) => line.trim())
    .filter((line) => line.length > 0)

  return {
    lines: lines.slice(0, max),
    total: lines.length,
    truncated: lines.length > max,
  }
}
