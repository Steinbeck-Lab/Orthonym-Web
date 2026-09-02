// The batch layer's pure arithmetic and vocabulary, kept out of the
// components so it can be tested without a DOM.
//
// The status words are the server's: JobState in backend/app/schemas.py is
// "queued" | "running" | "done" | "failed" | "cancelled". This file must not
// invent a sixth.

/** Rows per page in the results table. The server caps `limit` at 1000. */
export const PAGE_SIZE = 50

/** Statuses after which nothing more will change, so polling must stop. */
export const TERMINAL_STATES = new Set(['done', 'failed', 'cancelled'])

export function isTerminal(status) {
  return TERMINAL_STATES.has(status)
}

/**
 * How many pages `retrievable` rows make.
 *
 * Paginate against `retrievable`, never `total`: `total` is what was
 * submitted and `retrievable` is what can actually be read back, and on a
 * failed job the second is short of the first (JobResultsResponse says so).
 * Paging against `total` would offer pages that answer with nothing.
 */
export function pageCount(retrievable, pageSize = PAGE_SIZE) {
  if (!Number.isFinite(retrievable) || retrievable <= 0) return 0
  return Math.ceil(retrievable / pageSize)
}

/** Keeps a page number inside the pages that exist. Pages are 0-based. */
export function clampPage(page, retrievable, pageSize = PAGE_SIZE) {
  const count = pageCount(retrievable, pageSize)
  if (count === 0) return 0
  if (!Number.isFinite(page)) return 0
  return Math.min(Math.max(Math.trunc(page), 0), count - 1)
}

/**
 * Progress as a whole percentage.
 *
 * `done` counts molecules the workers have finished, failures included --
 * `failed` is a subset of `done`, not a separate bucket to add on. Summing
 * them would run a job with any failures past 100%.
 */
export function progressPercent({ done = 0, total = 0 } = {}) {
  if (!Number.isFinite(total) || total <= 0) return 0
  const ratio = Math.max(0, Math.min(1, done / total))
  return Math.round(ratio * 100)
}

/**
 * What to call a job's state in the interface.
 *
 * `cancelRequested` exists because of a race the backend documents and
 * accepts (redis_store.py: begin_chunk correctly refuses the next chunk after
 * a cancel, then _close_job writes "failed" over "cancelled"). Someone who
 * pressed Stop and is then told "failed" would reasonably think their data
 * broke, so a locally-remembered cancel wins the label. It only ever softens
 * the word -- it cannot claim a job finished.
 */
export function stateLabel(status, { cancelRequested = false } = {}) {
  if (cancelRequested && (status === 'failed' || status === 'cancelled')) {
    return 'Stopped'
  }
  switch (status) {
    case 'queued':
      return 'Queued'
    case 'running':
      return 'Running'
    case 'done':
      return 'Finished'
    case 'failed':
      return 'Failed'
    case 'cancelled':
      return 'Stopped'
    default:
      return 'Unknown'
  }
}

/**
 * How long until a job's results are deleted, in plain words.
 *
 * Job links are never to be presented as permanent (design spec section 14,
 * risk 2): the backend keeps results for 24 hours and this is the sentence
 * that says so wherever a link appears. Both arguments are UNIX seconds,
 * matching `expires_at`.
 */
export function expiryLabel(expiresAtSeconds, nowSeconds) {
  if (!Number.isFinite(expiresAtSeconds)) return null
  const remaining = expiresAtSeconds - nowSeconds
  if (remaining <= 0) return 'expired'
  const hours = Math.floor(remaining / 3600)
  if (hours >= 1) {
    return `expires in ${hours} hour${hours === 1 ? '' : 's'}`
  }
  const minutes = Math.max(1, Math.round(remaining / 60))
  return `expires in ${minutes} minute${minutes === 1 ? '' : 's'}`
}

/**
 * Whether pasted text has to run as a background job rather than inline.
 *
 * `fastPathMax` is the server's FAST_PATH_MAX_MOLECULES (10), mirrored in
 * parseSmiles.js as MAX_ROWS. Above it, /api/translate answers with a job
 * envelope instead of results, so the UI may as well submit a job on purpose
 * and show progress -- which is better than the old behaviour of refusing the
 * eleventh line.
 */
export function needsJob(moleculeCount, fastPathMax) {
  return Number.isFinite(moleculeCount) && moleculeCount > fastPathMax
}
