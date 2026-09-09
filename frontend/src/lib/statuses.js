// The status vocabulary, in one place.
//
// The backend's own copy is backend/app/schemas.py (Status, VERIFIED_STATUSES)
// -- this is the accepted cross-language mirror, since JS cannot import it.
// Within the frontend there must be exactly one: Tile and ConfidenceReport
// both render the confidence grammar, and two copies of "which tiers claim a
// round-trip" is how a tier ends up displayed as more confident than it is.

export const STATE_LABEL = {
  pin: 'Preferred IUPAC Name (PIN)',
  fallback: 'Not a verified PIN',
  // "did not confirm it" and not "could not round-trip check this": a
  // best-effort result covers BOTH the case where OPSIN parsed the name and
  // disagreed (roundtrip_smiles set, match false) and the case where OPSIN
  // could not parse it at all (roundtrip_smiles null). The old wording was
  // only true of the second, and claimed the check had not happened when it
  // usually had. The tile prints the actual verdict underneath either way.
  best_effort: 'Unverified best-effort name — OPSIN did not confirm it',
  abstain: 'Could not confidently name this',
  error: null, // uses the literal API error message instead
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
  best_effort: 'UNVERIFIED',
  abstain: 'NO NAME',
  error: 'BAD INPUT',
}

// Statuses that ship a real (if not always verified) name.
export const NAMED_STATUSES = new Set(['pin', 'fallback', 'best_effort'])

// Statuses whose confidence rule (double / dashed) claims an OPSIN round-trip
// confirmed the name. best_effort makes no such claim -- its own state label
// already says OPSIN did not confirm it -- so only these two need an
// explicit call-out when roundtrip_smiles is missing.
export const VERIFIED_STATUSES = new Set(['pin', 'fallback'])
