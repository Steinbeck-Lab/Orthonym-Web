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

// Statuses that ship a real (if not always verified) name.
export const NAMED_STATUSES = new Set(['pin', 'fallback', 'best_effort'])

// Statuses whose confidence rule (double / dashed) claims an OPSIN round-trip
// confirmed the name. best_effort makes no such claim -- its own state label
// already says OPSIN did not confirm it -- so only these two need an
// explicit call-out when roundtrip_smiles is missing.
export const VERIFIED_STATUSES = new Set(['pin', 'fallback'])
