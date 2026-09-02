// Where a submitted job's owner token lives.
//
// The server issues `owner_token` exactly once, in the response to
// POST /api/jobs, and never again. It is the only thing that authorises
// cancel and delete, because Orthonym has no accounts: ownership here IS
// possession of a secret handed to the submitter. Hold it only in React state
// and a page reload silently loses the ability to stop a 10,000-molecule job
// that will then hold one of the caller's two slots for its whole run.
//
// So it goes in localStorage, deliberately and with limits:
//   * this browser only -- nothing is sent anywhere, and there is no account
//     to attach it to;
//   * entries drop themselves once `expires_at` has passed, because the
//     server has deleted the job by then and a dead token is just a stale
//     secret sitting in someone's browser;
//   * the list is capped, so a heavy user does not accumulate tokens forever.
//
// Every access is wrapped: localStorage THROWS (not returns null) in a
// private window and wherever site data is blocked, and a hero page that
// crashes because storage is unavailable would be a much worse bug than
// forgetting a job.

const STORAGE_KEY = 'orthonym.jobs.v1'

/** Most recent jobs kept. Small on purpose: this is a convenience, not a log. */
export const MAX_REMEMBERED = 8

function storageOrNull() {
  try {
    return window.localStorage ?? null
  } catch {
    return null
  }
}

/**
 * Drops entries the server can no longer answer for. Pure, so the expiry
 * rule can be tested without a clock or a browser.
 */
export function pruneExpired(jobs, nowSeconds) {
  if (!Array.isArray(jobs)) return []
  return jobs.filter(
    (job) =>
      job &&
      typeof job.jobId === 'string' &&
      job.jobId.length > 0 &&
      (!Number.isFinite(job.expiresAt) || job.expiresAt > nowSeconds)
  )
}

/**
 * Puts `job` at the front, replacing any earlier entry for the same id, and
 * trims the list. Pure: the ordering rule is what matters and it is worth a
 * test of its own.
 */
export function withJob(jobs, job, { max = MAX_REMEMBERED } = {}) {
  const others = (Array.isArray(jobs) ? jobs : []).filter(
    (entry) => entry?.jobId !== job.jobId
  )
  return [job, ...others].slice(0, max)
}

/** Reads the remembered jobs, expired ones already dropped. */
export function readJobs(nowSeconds = Math.floor(Date.now() / 1000)) {
  const storage = storageOrNull()
  if (!storage) return []
  try {
    const raw = storage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    const live = pruneExpired(parsed, nowSeconds)
    // Written back so the pruning actually takes effect; a token whose job the
    // server has already deleted should not outlive it in a browser.
    if (Array.isArray(parsed) && live.length !== parsed.length) {
      storage.setItem(STORAGE_KEY, JSON.stringify(live))
    }
    return live
  } catch {
    // Unreadable or corrupt: behave exactly as if nothing was remembered.
    return []
  }
}

/**
 * Remembers one job. `expiresAt` may be unknown at submission time (the
 * envelope does not carry it — the first status poll does), and an entry
 * without it is kept rather than dropped; the next write fills it in.
 */
export function rememberJob({ jobId, ownerToken, moleculeCount, expiresAt = null }) {
  const storage = storageOrNull()
  if (!storage || !jobId) return readJobs()
  const entry = {
    jobId,
    ownerToken: ownerToken ?? null,
    moleculeCount: Number.isFinite(moleculeCount) ? moleculeCount : null,
    expiresAt: Number.isFinite(expiresAt) ? expiresAt : null,
    rememberedAt: Math.floor(Date.now() / 1000),
  }
  const next = withJob(readJobs(), entry)
  try {
    storage.setItem(STORAGE_KEY, JSON.stringify(next))
  } catch {
    // Full or blocked. The job still runs; only the convenience is lost.
  }
  return next
}

/** Forgets one job — after a delete, or when the server says it is gone. */
export function forgetJob(jobId) {
  const storage = storageOrNull()
  if (!storage) return []
  const next = readJobs().filter((entry) => entry.jobId !== jobId)
  try {
    storage.setItem(STORAGE_KEY, JSON.stringify(next))
  } catch {
    // See above: losing the convenience is acceptable, crashing is not.
  }
  return next
}

export { STORAGE_KEY as JOB_STORAGE_KEY }
