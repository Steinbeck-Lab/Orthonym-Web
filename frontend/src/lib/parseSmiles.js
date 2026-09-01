// Mirrors the backend's FAST_PATH_MAX_MOLECULES (backend/app/core/config.py),
// not a number of its own: one SMILES per line, blank/whitespace-only lines
// dropped, and only the first MAX_ROWS processed.
//
// This was 50 while the backend answered at most 10 inline, and the comment
// here claimed the two matched. Anything above 10 is not named inline at all
// -- POST /api/translate returns a job envelope and the caller is expected to
// poll -- and there is no batch UI yet, so every submission of 11-50
// molecules spent one of that IP's 20 hourly job units and real worker time
// producing results NO page in this app can fetch, then told the user to try
// again with fewer. Two units for one answer.
//
// 10 is the honest interim value. It goes back up when the batch UI lands and
// a job envelope becomes something the page can actually follow; until then
// the input must not invite a request the app cannot complete.
export const MAX_ROWS = 10

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
