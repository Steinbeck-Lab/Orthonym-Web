// Thin fetch wrappers around the OpenSTOUT showcase API.
// Contract:
//   GET  /api/health           -> { status: string }
//   GET  /api/examples         -> { examples: ExampleItem[] }
//   POST /api/translate        -> { results: ResultItem[] }
//   GET  /api/iupac-to-smiles  -> { smiles: string|null, depiction_svg: string|null, error: string|null }
//   GET  /api/explain          -> { smiles, name, svg, total_atoms, segments: ExplainSegment[], error }
//   GET  /api/explain-name     -> same shape, decomposing a typed IUPAC name directly
// See PRODUCT.md / DIRECTION brief for exact shapes. No fields are invented
// or hardcoded here — everything the UI shows comes from these responses.

const JSON_HEADERS = { 'Content-Type': 'application/json' }

/**
 * Hits the backend's own liveness probe. Resolves with the raw parsed body
 * on a 2xx response; rejects (with a message safe to show a visitor) on a
 * non-2xx response or a network-level failure (backend unreachable).
 * @returns {Promise<{status:string}>}
 */
export async function checkHealth() {
  const res = await fetch('/api/health')
  if (!res.ok) {
    throw new Error(`GET /api/health failed with ${res.status}`)
  }
  return res.json()
}

/**
 * @returns {Promise<{label:string, smiles:string, expected_status:string}[]>}
 */
export async function fetchExamples() {
  const res = await fetch('/api/examples')
  if (!res.ok) {
    throw new Error(`GET /api/examples failed with ${res.status}`)
  }
  const data = await res.json()
  return Array.isArray(data?.examples) ? data.examples : []
}

/**
 * @param {string[]} smilesList
 * @returns {Promise<{smiles:string, status:string, name:string|null, tier:string|null, formula:string|null, limit_code:string|null, error:string|null, depiction_svg:string|null, roundtrip_smiles:string|null, roundtrip_match:boolean|null}[]>}
 */
export async function translateBatch(smilesList, { bestEffort = true } = {}) {
  const res = await fetch('/api/translate', {
    method: 'POST',
    headers: JSON_HEADERS,
    // best_effort defaults to true server-side too, so an older caller that
    // omits it keeps the shipped behaviour. False stops after the primary
    // namer, which means no OPSIN-unverified name can come back at all.
    body: JSON.stringify({ smiles: smilesList, best_effort: bestEffort }),
  })
  if (!res.ok) {
    throw new Error(`POST /api/translate failed with ${res.status}`)
  }
  const data = await res.json()
  return Array.isArray(data?.results) ? data.results : []
}

/**
 * Looks up the structure for a single IUPAC name via the backend's OPSIN-
 * backed converter. A name that fails to parse is not a thrown error here —
 * it comes back as a normal 2xx response with `error` set and `smiles` /
 * `depiction_svg` both null; only a network-level failure or non-2xx status
 * rejects the promise.
 * @param {string} name
 * @returns {Promise<{smiles:string|null, depiction_svg:string|null, error:string|null}>}
 */
export async function fetchStructureFromName(name) {
  const res = await fetch(`/api/iupac-to-smiles?name=${encodeURIComponent(name)}`)
  if (!res.ok) {
    throw new Error(`GET /api/iupac-to-smiles failed with ${res.status}`)
  }
  return res.json()
}

/**
 * Names `smiles` (the same way /api/translate would) and decomposes that
 * name into a TREE of hoverable segments, each paired with real RDKit atom
 * indices where that correspondence could be established reliably.
 *
 * Failure is per part, not per molecule: a part whose atoms could not be
 * pinned down comes back as an ordinary segment with `kind: "unmapped"`,
 * empty `atom_indices`/`highlight_atoms` and its siblings intact. A molecule
 * STITCH can't confidently name at all is not an error either — it comes
 * back as a normal 2xx response with `error` set; only a network-level
 * failure or non-2xx status rejects the promise.
 * @param {string} smiles
 * @returns {Promise<{smiles:string, name:string|null, svg:string|null, total_atoms:number, segments:Array<{label:string,kind:string,owns_atoms:boolean,locant:string|null,explanation:string,atom_indices:number[],highlight_atoms:number[],name_range:[number,number]|null,children:object[]}>, error:string|null}>}
 */
export async function explainMolecule(smiles) {
  const res = await fetch(`/api/explain?smiles=${encodeURIComponent(smiles)}`)
  if (!res.ok) {
    throw new Error(`GET /api/explain failed with ${res.status}`)
  }
  return res.json()
}

/**
 * Decomposes an IUPAC name directly, without going through a structure
 * first. A name OPSIN cannot parse is not a network error - it returns a
 * normal 2xx response with `error` set.
 * @param {string} name
 * @returns {Promise<object>}
 */
export async function explainName(name) {
  const res = await fetch(`/api/explain-name?name=${encodeURIComponent(name)}`)
  if (!res.ok) {
    throw new Error(`GET /api/explain-name failed with ${res.status}`)
  }
  return res.json()
}
