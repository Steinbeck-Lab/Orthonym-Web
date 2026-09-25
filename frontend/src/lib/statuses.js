// The status vocabulary, in one place.
//
// The backend's own copy is backend/app/schemas.py (Status, VERIFIED_STATUSES)
// -- this is the accepted cross-language mirror, since JS cannot import it.
// Within the frontend there must be exactly one: Tile and ConfidenceReport
// both render the confidence grammar, and two copies of "which tiers claim a
// round-trip" is how a tier ends up displayed as more confident than it is.

export const STATE_LABEL = {
  pin: 'Preferred IUPAC Name (PIN)',
  // Engine tiers systematic_verified AND pin_unverified: both round-trip, and
  // the engine does not certify either as the PIN.
  fallback: 'Verified name, preferred status not certified',
  // WHERE the name came from, never a verdict: the engine round-trips every
  // name it emits, best_effort included, and the tile prints this app's own
  // round-trip verdict underneath. A best_effort row with no round trip here
  // takes UNCHECKED_LABEL instead (stateLabelFor, below).
  best_effort: 'Best-effort name from the general engine',
  abstain: 'Could not confidently name this',
  error: null, // uses the literal API error message instead
}

// A best_effort row with no round-trip result from this app: OPSIN verify
// off, an input RDKit cannot read, or a name OPSIN cannot read back. The
// backend demotes a pin or fallback to best_effort in exactly that case and
// keeps the engine's tier, so "from the general engine" would be false of it.
// Keyed on the missing round trip, not on the tier, because batch rows carry
// no tier -- and "not checked here" is true of every such row.
export const UNCHECKED_LABEL = 'Name not checked here: no round-trip result'

/** A best_effort row with no round-trip result here. ONE test, read by the
 *  label below and by Tile's line under it, so the two cannot disagree. */
export function isUncheckedHere(row) {
  return row?.status === 'best_effort' && !row.roundtrip_smiles
}

// A best_effort row whose round trip here RAN and read back a different
// molecule. The backend demotes a pin or fallback to best_effort in that case
// too, so "from the general engine" would be false of it; "a different
// structure" is true of every such row, whatever built the name.
export const MISMATCH_LABEL = 'Round trip here gave a different structure'

/** A best_effort row whose round trip here did not match. */
export function isMismatchHere(row) {
  return row?.status === 'best_effort' && Boolean(row.roundtrip_smiles) && row.roundtrip_match === false
}

/** The long tier label for one row. Every surface that prints one calls this,
 *  so the unchecked and mismatch cases cannot be missed on any of them. */
export function stateLabelFor(row) {
  if (isUncheckedHere(row)) return UNCHECKED_LABEL
  if (isMismatchHere(row)) return MISMATCH_LABEL
  return STATE_LABEL[row?.status]
}

// API status values use underscores (e.g. "best_effort"); CSS state classes
// use hyphens (e.g. "tile--best-effort") per the existing tile--pin /
// tile--fallback / tile--abstain / tile--error naming.
export const STATE_CLASS = {
  pin: 'pin',
  fallback: 'fallback',
  best_effort: 'best-effort',
  abstain: 'abstain',
  error: 'error',
}

// The ladder, strongest first. ONE list, because two places now walk it:
// ConfidenceLegend teaches the vocabulary and the batch tally counts in it,
// and a second copy is how the two end up disagreeing about the order.
export const TIER_ORDER = ['pin', 'fallback', 'best_effort', 'abstain', 'error']

// The SHORT word the interface puts next to a name -- the one a reader meets
// in the confidence key and in a batch tally. STATE_LABEL above is the long
// form a single result tile prints; this is the same tier said in one or two
// words, and the two must never drift apart.
export const STATE_SHORT = {
  pin: 'PIN',
  fallback: 'FALLBACK',
  best_effort: 'BEST EFFORT',
  abstain: 'NO NAME',
  // Not "BAD INPUT": an error row is also a naming crash or a batch timeout.
  error: 'ERROR',
}

// Statuses that ship a real name, whatever its tier.
export const NAMED_STATUSES = new Set(['pin', 'fallback', 'best_effort'])

// Statuses whose confidence rule (double / dashed) claims an OPSIN round-trip
// confirmed the name. best_effort makes no such claim -- its label names the
// general engine, or says outright that no round trip ran here -- so only
// these two need an explicit call-out when roundtrip_smiles is missing.
export const VERIFIED_STATUSES = new Set(['pin', 'fallback'])
