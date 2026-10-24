// Why a row has no name, in one plain sentence, keyed on its `limit_code`.
//
// Upper-case codes are the Orthonym engine's own (orthonym/errors.py,
// LIMIT_CATALOG); lower-case ones are this app's (backend/app/schemas.py).
// A code missing here is shown raw rather than hidden: a new engine code must
// never turn a reason into silence.

const REASONS = Object.freeze({
  WILDCARD_ATOMS: 'The structure has wildcard atoms (*), which no IUPAC name can express.',
  UNSUPPORTED_ELEMENT: 'The structure has an element the engine does not name yet, such as a metal.',
  ISOLATED_ATOM: 'The structure is a single atom or a fragment too small to name as a compound.',
  STRUCTURE_TOO_LARGE: 'The engine found no name for this structure, which is above its heavy-atom limit.',
  UNSUPPORTED_RING_SYSTEM:
    'The engine knows this ring system but cannot name it correctly yet, so it declines rather than guess.',
  UNNAMEABLE: 'The engine has no rule that names this structure yet.',
  NO_VERIFIED_PIN: 'The engine built a name but could not verify it, so it is not shown.',
  withheld_unchecked:
    'The engine found a name, but no round trip checked it and best effort is off, so it is not shown. Turn best effort on to see it.',
  timeout: 'Naming took too long and was stopped.',
  engine_error: 'The engine stopped with an internal error on this structure.',
})

const UNNAMED = new Set(['abstain', 'error'])

/** The reason sentence for an abstain or error row, or null. */
export function limitReasonFor(row) {
  if (!row?.limit_code || !UNNAMED.has(row.status)) return null
  return REASONS[row.limit_code] ?? `Reason code: ${row.limit_code}`
}
