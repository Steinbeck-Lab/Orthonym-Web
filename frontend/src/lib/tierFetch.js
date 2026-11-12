// The confidence tier /explain and /compare fetch beside a breakdown, as a
// state rather than a bare row. Every failure used to become "no row", so the
// page showed an engine name with no tier and no word about why (PRODUCT.md
// principle 3: the tier is visible wherever a name appears, or its absence is
// said). Kept out of useExplain.js so a node test can reach it.

import { cancelJob, translateBatch, TranslateJobQueuedError } from './api.js'
import { transportMessage } from './transport.js'

export const TIER_IDLE = { status: 'idle', row: null, reason: null }
export const TIER_LOADING = { status: 'loading', row: null, reason: null }

/** Why the tier could not be had, in the reader's words. */
export function tierFailureReason(error) {
  if (error instanceof TranslateJobQueuedError) {
    return 'the naming service was busy, so the request was queued instead of answered. Try again shortly.'
  }
  return transportMessage(error) ?? 'could not reach Orthonym’s backend.'
}

/**
 * One /api/translate call for `smiles`. Never rejects: resolves to
 * { status: 'ready', row } or { status: 'failed', reason }.
 *
 * A queued answer means a real job is running that nothing will watch, and its
 * owner token is only ever issued here, so it is cancelled now (as the About
 * page's round-trip loop does).
 */
export async function fetchTier(smiles, settings, { translate = translateBatch, cancel = cancelJob } = {}) {
  try {
    const rows = await translate([smiles], settings)
    const row = rows?.[0] ?? null
    if (row) return { status: 'ready', row, reason: null }
    return { status: 'failed', row: null, reason: 'the server returned no result for this structure.' }
  } catch (error) {
    if (error instanceof TranslateJobQueuedError && error.ownerToken) {
      Promise.resolve()
        .then(() => cancel(error.jobId, error.ownerToken))
        .catch(() => {})
    }
    return { status: 'failed', row: null, reason: tierFailureReason(error) }
  }
}

/** The line shown in place of the tier while it is pending or after it failed;
 *  null when there is a row (or nothing was asked). */
export function tierNote(state) {
  if (state?.status === 'loading') return 'Checking the confidence tier…'
  if (state?.status === 'failed') return `Confidence tier unavailable: ${state.reason}`
  return null
}
