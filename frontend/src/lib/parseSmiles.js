// Mirrors the backend's own input handling exactly (see API CONTRACT):
// one SMILES per line, blank/whitespace-only lines dropped, and if more
// than 50 non-blank lines remain, only the first 50 are processed.
export const MAX_ROWS = 50

export function parseSmilesLines(rawText) {
  const lines = rawText
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line.length > 0)

  return {
    lines: lines.slice(0, MAX_ROWS),
    total: lines.length,
    truncated: lines.length > MAX_ROWS,
  }
}
