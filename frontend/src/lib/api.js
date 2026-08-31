// Thin fetch wrappers around the OpenSTOUT showcase API.
// Contract:
//   GET  /api/health           -> { status: string, opsin: string }
//   GET  /api/examples         -> { examples: ExampleItem[] }
//   POST /api/translate        -> { results: ResultItem[] } OR, when the
//                                  submission doesn't finish inside the
//                                  server's fast-path timeout, a job
//                                  envelope { job_id, molecule_count, status }
//                                  -- see TranslateJobQueuedError below.
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
 * `opsin` reports whether at least one Celery worker has a live JVM -- see
 * HealthResponse in backend/app/schemas.py; "DEGRADED" is what makes every
 * naming endpoint 503 rather than serving an unverified tier.
 * @returns {Promise<{status:string, opsin:string}>}
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
 * Thrown by translateBatch when the backend hands back a job envelope
 * (`{job_id, molecule_count, status}`, from POST /api/translate) instead of
 * finished results -- the submission didn't finish inside the server's
 * fast-path timeout (too many molecules, or a slow one), so the backend
 * queued it as a background job rather than blocking the request. STITCH's
 * frontend has no batch-job polling UI (a separate, larger project), so
 * there is nothing useful this promise can resolve with; throwing lets the
 * caller tell this apart from "zero results" and say something true
 * instead of silently rendering an empty grid.
 */
export class TranslateJobQueuedError extends Error {
  constructor(jobId, moleculeCount) {
    super(
      `Submission queued as background job ${jobId} (${moleculeCount} molecule` +
        `${moleculeCount === 1 ? '' : 's'}) instead of returning immediately.`
    )
    this.name = 'TranslateJobQueuedError'
    this.jobId = jobId
    this.moleculeCount = moleculeCount
  }
}

/**
 * @param {string[]} smilesList
 * @returns {Promise<{smiles:string, status:string, name:string|null, tier:string|null, formula:string|null, limit_code:string|null, error:string|null, depiction_svg:string|null, roundtrip_smiles:string|null, roundtrip_match:boolean|null}[]>}
 * @throws {TranslateJobQueuedError} when the backend queues the submission
 *   as a background job instead of returning results directly (see above).
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
  // A job envelope carries `job_id`; a finished TranslateResponse never
  // does (see JobEnvelope's own docstring in backend/app/schemas.py: "tell
  // it apart from a completed response by the presence of job_id"). This
  // used to fall through to `Array.isArray(data?.results) ? ... : []`,
  // which made a queued job indistinguishable from a genuine empty result
  // set -- real work would be running on the server while the UI told the
  // user nothing at all.
  if (data?.job_id) {
    throw new TranslateJobQueuedError(data.job_id, data.molecule_count)
  }
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
