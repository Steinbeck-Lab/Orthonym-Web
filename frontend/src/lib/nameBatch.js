import { splitLines } from './parseLines.js'

/**
 * How many IUPAC names one submission may convert.
 *
 * Derived from a backend limit, not invented: each name is one
 * GET /api/iupac-to-smiles, and that endpoint calls check_fast_allowed(ip) --
 * the shared naming budget of RATE_LIMIT_FAST_PER_MINUTE = 60 per IP per
 * minute (backend/app/core/config.py). 25 leaves headroom for a second
 * attempt inside the same minute and for the depiction requests the page
 * also makes. Raise it only alongside that budget, or by moving to a real
 * batch endpoint.
 */
export const MAX_NAMES = 25

export function parseNameLines(rawText) {
  const { lines, total, truncated } = splitLines(rawText, MAX_NAMES)
  return { names: lines, total, truncated }
}

/**
 * Convert `names` by calling `fetchOne` for each, at most `concurrency` at a
 * time, and resolve to rows IN INPUT ORDER.
 *
 * Input order is the contract, not an accident: the table numbers its rows,
 * and a row whose number does not match the line the user pasted attaches
 * every identifier to the wrong name.
 *
 * `fetchOne` is injected so the tests never touch the network.
 *
 * Concurrency 4, not "all at once": each request occupies a slot on the
 * `fast` Celery queue and the workers run at -c 2, so an unbounded fan-out
 * only queues in Redis while holding 25 open HTTP connections. Four keeps
 * both workers busy with a short queue.
 *
 * Nothing here rejects. A failure is a row, because a partial answer to 25
 * names beats no answer, and one bad line says nothing about the next.
 */
export async function convertNames(names, { fetchOne, onProgress, concurrency = 4 } = {}) {
  const rows = new Array(names.length)
  let next = 0
  let done = 0

  async function worker() {
    while (true) {
      const index = next
      next += 1
      if (index >= names.length) return

      const name = names[index]
      try {
        const data = await fetchOne(name)
        rows[index] = data?.error
          ? { index, name, ok: false, data: null, error: data.error }
          : { index, name, ok: true, data, error: null }
      } catch (err) {
        rows[index] = {
          index,
          name,
          ok: false,
          data: null,
          error: err?.message || 'Could not convert this name',
        }
      }
      done += 1
      // A failure advances the bar too, or a batch containing one bad name
      // stalls short of its total and reads as hung.
      //
      // Guarded on its own, and NOT moved inside the try above: this module
      // promises it never rejects, and a caller's progress callback is the one
      // piece of code here that this module does not own. Without this guard a
      // throwing onProgress escapes worker(), rejects the Promise.all, and takes
      // the whole batch down -- losing rows that had already succeeded. Inside
      // the fetch try instead, a caught fetch error would skip the call and the
      // bar would stall short of its total.
      try {
        onProgress?.(done, names.length)
      } catch {
        // A broken progress display is not a reason to lose the results.
      }
    }
  }

  const size = Math.max(1, Math.min(concurrency, names.length))
  await Promise.all(Array.from({ length: size }, worker))
  return rows
}
