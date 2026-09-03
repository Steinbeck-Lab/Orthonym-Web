/**
 * Split pasted text into trimmed, non-blank lines, capped at `max`.
 *
 * `total` is the count BEFORE the cap, deliberately: the UI tells the user
 * how many lines they pasted and how many will be processed, and reporting
 * the capped number instead would hide the drop.
 */
export function splitLines(rawText, max) {
  const lines = String(rawText ?? '')
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line.length > 0)

  return {
    lines: lines.slice(0, max),
    total: lines.length,
    truncated: lines.length > max,
  }
}
