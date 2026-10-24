// Why the engine declined to name a molecule (an abstain row), in one plain
// sentence keyed on its `limit_code`.
//
// Upper-case codes are the Orthonym engine's own (orthonym/errors.py,
// LIMIT_CATALOG); lower-case ones are this app's (backend/app/schemas.py).
// A code missing here is shown raw rather than hidden: a new engine code must
// never turn a reason into silence.

const REASONS = Object.freeze({
  WILDCARD_ATOMS: 'The structure has wildcard atoms (*), which no IUPAC name can express.',
  UNSUPPORTED_ELEMENT: 'The structure has an element the engine does not name yet, such as a metal.',
  ISOLATED_ATOM: 'The structure is a single atom or a fragment too small to name as a compound.',
  STRUCTURE_TOO_LARGE: 'The engine found no name for this structure, which has more than 125 heavy atoms.',
  UNSUPPORTED_RING_SYSTEM:
    'The engine knows this ring system but cannot name it correctly yet, so it declines rather than guess.',
  UNNAMEABLE: 'The engine has no rule that names this structure yet.',
  NO_VERIFIED_PIN: 'The engine built a name, but not a verified preferred IUPAC name, so it is not shown.',
  withheld_unchecked:
    'The engine found a name, but no round trip checked it and best effort is off, so it is not shown. Turn best effort on to see it.',
  roundtrip_mismatch: 'OPSIN read this name back as a different structure, so it is not shown.',
})

/** The reason sentence for an abstain row, or null. An error row gets none:
 *  its own message already says what failed. */
export function limitReasonFor(row) {
  if (row?.status !== 'abstain' || !row.limit_code) return null
  return REASONS[row.limit_code] ?? `Reason code: ${row.limit_code}`
}
