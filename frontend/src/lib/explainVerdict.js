// What /explain is allowed to CLAIM about a result, as data rather than markup.
//
// Both decisions here used to live inside Explain.jsx's and ConfidenceReport's
// JSX. They are pulled out for one blunt reason: `npm test` is
// `node --test "src/**/*.test.js"` with no transform step, so a file
// containing JSX cannot be imported by a test at all. A decision that stays in
// a .jsx file is a decision no test in this repo can reach, and both of these
// are decisions about how confident STITCH claims to be -- PRODUCT.md
// principle 3, the thing the product is for. They belong somewhere provable.
//
// Neither function knows anything about React, tabs, or the DOM.

import { NAMED_STATUSES, VERIFIED_STATUSES } from './statuses.js'

/**
 * Which claim /explain may make about the name it is showing.
 *
 * The argument is the mode the DISPLAYED RESULT WAS FETCHED WITH, and never
 * the input tab that happens to be selected right now. That distinction is the
 * whole reason this function exists as its own named thing: the two were the
 * same variable until 2026-09-05, and because a tab can be changed after a
 * result has landed, switching tabs rewrote the verdict without re-running
 * anything -- a real PIN was replaced by "there is no confidence tier for
 * this", and in the other direction the honest disclosure silently vanished.
 *
 * 'stitch-verdict'   STITCH produced this name, so its tier is a real verdict
 *                    and principle 3 requires showing it.
 * 'user-supplied'    the user typed the name; STITCH has no opinion on it, and
 *                    inventing a tier mark would misrepresent confidence.
 * 'none'             nothing has been explained yet.
 *
 * @param {'name'|'smiles'|'draw'|null|undefined} resultMode
 */
export function verdictKindFor(resultMode) {
  if (resultMode === null || resultMode === undefined) return 'none'
  return resultMode === 'name' ? 'user-supplied' : 'stitch-verdict'
}

/**
 * The round-trip proof line beneath a tier, as parts.
 *
 * ONE voice, which is the point. This used to be two spellings chosen by a
 * Learn/Expert switch; the switch was removed and the spellings merged rather
 * than one deleted, so the sentence says in plain words what the check DID and
 * still carries the SMILES it produced -- determinism is proven, not asserted
 * (principle 1), and the proof is the string.
 *
 * Returns null when there is no line to draw, which is not the same as an
 * empty one: a tier whose rule CLAIMS a round-trip confirmed it must never
 * fall silent, because an absent line looks identical to a tier that makes no
 * such claim. That case returns `available: false` instead.
 *
 * @param {{status: string, roundtrip_smiles?: string|null, roundtrip_match?: boolean}|null} row
 */
export function roundtripLine(row) {
  if (!row || !NAMED_STATUSES.has(row.status)) return null
  const { status, roundtrip_smiles, roundtrip_match } = row

  if (roundtrip_smiles) {
    return {
      available: true,
      lead: 'Round-trip check: we read this name back and it gives',
      result: roundtrip_match ? 'the same molecule ✓' : 'a different molecule ✗',
      match: Boolean(roundtrip_match),
      smiles: roundtrip_smiles,
    }
  }

  // No proof came back. Only a tier that CLAIMED one owes an explanation.
  if (VERIFIED_STATUSES.has(status)) {
    return {
      available: false,
      lead: 'Round-trip check:',
      result: 'unavailable',
      tail: '— we could not read this name back, so this result is not confirmed.',
    }
  }

  return null
}
