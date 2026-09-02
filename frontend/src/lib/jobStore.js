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

// The status vocabulary and the terminal test belong to batchJob.js -- this
// module must not invent a second opinion about what "finished" means. The
// extension is required: `node --test` resolves this file for real, and it
// does not do Vite's extensionless lookup (svgHighlight.js is imported the
// same way, for the same reason).
import { isTerminal } from './batchJob.js'

// v2, and the bump is the fix rather than housekeeping. v1 remembered a job
// for as long as the server would keep it -- 24 hours -- so a FINISHED batch
// came back on every reload, including a hard reload, which cannot clear
// localStorage. Nothing in the app could shift it and it read as the page
// being stuck. The store now holds only jobs that might still need stopping
// (see rememberJob and BatchResults), and the new key retires every v1 entry
// on the first load rather than restoring one last stale panel.
const STORAGE_KEY = 'orthonym.jobs.v2'
const RETIRED_KEYS = ['orthonym.jobs.v1']

/** Most recent jobs kept. Small on purpose: this is a convenience, not a log. */
export const MAX_REMEMBERED = 8

/**
 * How long an entry may live without a known expiry.
 *
 * `expiresAt` arrives on the first successful status poll, not with the
 * submission, so a job submitted while the backend was unreachable keeps
 * `expiresAt: null` -- and pruneExpired deliberately keeps those, so without
 * a bound it would sit in a browser forever, restoring a panel for a job the
 * server has long since deleted. 24 hours is JOB_RESULT_TTL_SECONDS: past it
 * there is nothing left to own.
 */
export const UNKNOWN_EXPIRY_MAX_AGE_SECONDS = 24 * 60 * 60

// The v1 retirement is a MIGRATION: it has to happen before the first read,
// and exactly once. Doing it inside storageOrNull ran removeItem twice per
// rememberJob/forgetJob (each of those resolves the storage itself and then
// again via readJobs) for the whole life of the tab, long after the key was
// gone.
let retired = false

function storageOrNull() {
  try {
    const storage = window.localStorage ?? null
    if (storage && !retired) {
      retired = true
      // A superseded schema left in place is dead weight that only ever
      // confuses the next reader of a browser's storage panel.
      for (const key of RETIRED_KEYS) storage.removeItem(key)
    }
    return storage
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
  return jobs.filter((job) => {
    if (!job || typeof job.jobId !== 'string' || job.jobId.length === 0) return false
    if (Number.isFinite(job.expiresAt)) return job.expiresAt > nowSeconds
    // Expiry unknown: fall back to when it was remembered, so an entry whose
    // first status poll never landed still ages out instead of living
    // forever. rememberJob always stamps that, so every real entry is
    // bounded; one carrying neither date is kept, because a job submitted a
    // moment ago is the one whose token matters most.
    if (!Number.isFinite(job.rememberedAt)) return true
    return job.rememberedAt + UNKNOWN_EXPIRY_MAX_AGE_SECONDS > nowSeconds
  })
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
export function rememberJob({ jobId, ownerToken, moleculeCount, expiresAt = null, status = null }) {
  const storage = storageOrNull()
  if (!storage || !jobId) return readJobs()
  // THE STORE ENFORCES ITS OWN RULE. "Never persist a terminal job" is the
  // whole point of this module, and it used to be enforced only by
  // BatchResults calling forgetJob at the right moment -- so any other
  // caller that remembered a job without checking first would silently
  // reintroduce the bug where a finished batch came back on every reload.
  // Home already calls this from two places. A terminal status now removes
  // the entry instead of writing it, and callers with no status to offer
  // (the submission envelope's own "queued", a poll filling in an expiry)
  // are unaffected.
  if (isTerminal(status)) return forgetJob(jobId)
  const entry = {
    jobId,
    ownerToken: ownerToken ?? null,
    moleculeCount: Number.isFinite(moleculeCount) ? moleculeCount : null,
    expiresAt: Number.isFinite(expiresAt) ? expiresAt : null,
    status: status ?? null,
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
