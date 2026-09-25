// Thin fetch wrappers around the Orthonym backend API.
// Contract:
//   GET  /api/health           -> { status: string, opsin: string }
//   GET  /api/examples         -> { examples: ExampleItem[] }
//   POST /api/translate        -> { results: ResultItem[] } OR, when the
//                                  submission doesn't finish inside the
//                                  server's fast-path timeout, a job
//                                  envelope { job_id, molecule_count, status }
//                                  -- see TranslateJobQueuedError below.
//   GET  /api/iupac-to-smiles  -> { smiles, canonical_smiles, inchi, inchikey,
//                                   molblock, depiction_svg, error } -- every
//                                   field string|null. The four identifier
//                                   fields are independently optional: RDKit's
//                                   InChI writer and 2D coordinate generation
//                                   are not total, and losing one must not
//                                   cost the others.
//   GET  /api/explain          -> { smiles, name, svg, total_atoms, segments: ExplainSegment[], error }
//   GET  /api/explain-name     -> same shape, decomposing a typed IUPAC name directly
//
// The batch/job layer (one submission, many molecules, answered over time):
//   POST   /api/parse-preview       -> { format, molecule_count, sample[], errors[] }
//   POST   /api/jobs                -> JobEnvelope { job_id, molecule_count, status, owner_token }
//   GET    /api/jobs/{id}           -> { job_id, status, total, done, failed, created_at, expires_at }
//   GET    /api/jobs/{id}/results   -> { job_id, offset, limit, total, retrievable, rows[] }
//   GET    /api/jobs/{id}/results.csv (a plain link, fetched by the browser)
//   POST   /api/jobs/{id}/cancel?owner_token=…
//   DELETE /api/jobs/{id}?owner_token=…
//   GET    /api/depict?smiles=…     -> { depiction_svg, error }
//
// See PRODUCT.md / DIRECTION brief for exact shapes. No fields are invented
// or hardcoded here — everything the UI shows comes from these responses.

const JSON_HEADERS = { 'Content-Type': 'application/json' }

/**
 * Hits the backend's own liveness probe. Resolves with the raw parsed body
 * on a 2xx response; rejects (with a message safe to show a visitor) on a
 * non-2xx response or a network-level failure (backend unreachable).
 * `opsin` reports whether at least one Celery worker has a live JVM -- see
 * HealthResponse in backend/app/schemas.py; "DEGRADED" is what makes every
 * naming endpoint 503 rather than serving a tier SELF-01 never checked.
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
 * (a full `JobEnvelope`, from POST /api/translate) instead of finished
 * results -- the submission didn't finish inside the server's fast-path
 * timeout, so the backend queued it as a background job rather than blocking
 * the request.
 *
 * It carries the envelope's `owner_token`, which is the point: the token is
 * issued exactly once, and Home now hands the whole job to the batch panel
 * to watch, stop and download. Dropping it here (as this did while there was
 * no batch UI) meant the queued job could never be cancelled by the person
 * who started it.
 */
export class TranslateJobQueuedError extends Error {
  constructor(jobId, moleculeCount, ownerToken) {
    super(
      `Submission queued as background job ${jobId} (${moleculeCount} molecule` +
        `${moleculeCount === 1 ? '' : 's'}) instead of returning immediately.`
    )
    this.name = 'TranslateJobQueuedError'
    this.jobId = jobId
    this.moleculeCount = moleculeCount
    this.ownerToken = ownerToken ?? null
  }
}

/**
 * @param {string[]} smilesList
 * @returns {Promise<{smiles:string, status:string, name:string|null, tier:string|null, formula:string|null, limit_code:string|null, error:string|null, depiction_svg:string|null, roundtrip_smiles:string|null, roundtrip_match:boolean|null}[]>}
 * @throws {TranslateJobQueuedError} when the backend queues the submission
 *   as a background job instead of returning results directly (see above).
 */
export async function translateBatch(smilesList, { bestEffort = true, verify = true } = {}) {
  const res = await fetch('/api/translate', {
    method: 'POST',
    headers: JSON_HEADERS,
    // best_effort defaults to true server-side too, so an older caller that
    // omits it keeps the shipped behaviour. False stops after the primary
    // namer: no second, escalated pass. (The primary namer can still return
    // tier best_effort for some names.)
    body: JSON.stringify({ smiles: smilesList, best_effort: bestEffort, verify }),
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
    throw new TranslateJobQueuedError(data.job_id, data.molecule_count, data.owner_token)
  }
  return Array.isArray(data?.results) ? data.results : []
}

/**
 * Looks up the structure for a single IUPAC name via the backend's OPSIN-
 * backed converter. A name that fails to parse is not a thrown error here —
 * it comes back as a normal 2xx response with `error` set and `smiles`,
 * `canonical_smiles`, `inchi`, `inchikey`, `molblock` and `depiction_svg` all
 * null; only a network-level failure or non-2xx status rejects the promise.
 * The rejection's `status` carries the HTTP status code (when one exists —
 * a genuine network failure has none) so a caller can tell a rate limit or a
 * degraded backend apart from real unreachability.
 * @param {string} name
 * @returns {Promise<{smiles:string|null, canonical_smiles:string|null, inchi:string|null, inchikey:string|null, molblock:string|null, depiction_svg:string|null, error:string|null}>}
 */
export async function fetchStructureFromName(name) {
  const res = await fetch(`/api/iupac-to-smiles?name=${encodeURIComponent(name)}`)
  if (!res.ok) {
    const err = new Error(`GET /api/iupac-to-smiles failed with ${res.status}`)
    err.status = res.status
    throw err
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
 * Orthonym can't confidently name at all is not an error either — it comes
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

/* ------------------------------------------------------------------ *
 * The job layer
 * ------------------------------------------------------------------ */

/**
 * A job the server will not talk about any more: either it never existed, or
 * it has expired (the backend distinguishes 404 from 410 and so does this).
 * Carried as its own error type because the UI has to say something DIFFERENT
 * for "gone" than for "broken" — a 24-hour-old link is an expected outcome,
 * not a fault.
 */
export class JobGoneError extends Error {
  constructor(jobId, status) {
    super(
      status === 410
        ? `Job ${jobId} has expired. Job results are kept for 24 hours.`
        : `No job ${jobId}. It may never have existed, or its results were deleted.`
    )
    this.name = 'JobGoneError'
    this.jobId = jobId
    this.expired = status === 410
    this.status = status
  }
}

/** Too many requests. Carries the server's own retry hint when it sent one. */
export class RateLimitedError extends Error {
  constructor(retryAfterSeconds) {
    super(
      retryAfterSeconds
        ? `Rate limited. Try again in ${retryAfterSeconds} seconds.`
        : 'Rate limited. Try again shortly.'
    )
    this.name = 'RateLimitedError'
    this.retryAfterSeconds = retryAfterSeconds ?? null
  }
}

/**
 * Turns a non-2xx job response into the most specific error available.
 * The backend puts a human sentence in `detail` for every 4xx it raises
 * deliberately (413 over the size cap, 400 for an unusable body, 409 for a
 * job that cannot be deleted yet), and showing that sentence is the whole
 * reason it exists. A response with no readable body falls back to the status.
 */
async function jobFailure(res, jobId) {
  if (res.status === 404 || res.status === 410) {
    return new JobGoneError(jobId, res.status)
  }
  if (res.status === 429) {
    const retry = Number.parseInt(res.headers.get('retry-after') ?? '', 10)
    return new RateLimitedError(Number.isFinite(retry) ? retry : null)
  }
  let detail = null
  try {
    const body = await res.json()
    detail = typeof body?.detail === 'string' ? body.detail : null
  } catch {
    // A body that is not JSON tells us nothing extra; the status still does.
  }
  return new Error(detail ?? `Request failed with ${res.status}`)
}

/**
 * Builds the request for the two endpoints that accept EITHER a file or
 * pasted text. A file goes as multipart (the only way `best_effort` can ride
 * along, as a form field); text goes as JSON `{text, best_effort}`. Sending a
 * file as JSON, or text as multipart, both 400 — see _read_input in
 * backend/app/jobs_api.py.
 */
function inputRequest({ file, text, bestEffort, verify = true }) {
  if (file) {
    const form = new FormData()
    form.append('file', file)
    form.append('best_effort', String(bestEffort))
    form.append('verify', String(verify))
    // No Content-Type header: the browser has to set the multipart boundary.
    return { method: 'POST', body: form }
  }
  return {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ text, best_effort: bestEffort, verify }),
  }
}

/**
 * Counts the molecules in an input and parses the FIRST FEW of them.
 *
 * `molecule_count` covers the whole input, but `sample` and `errors` come from
 * parsing only the first PREVIEW_SAMPLE records. An empty `errors` therefore
 * means "no errors in the first few", NOT "this file is clean" — the response
 * schema says so at length, and any UI that promises the latter will tell
 * someone their file is fine and then fail on row 6.
 * @returns {Promise<{format:string, molecule_count:number, sample:Array<{index:number,input:string,input_id:string|null,smiles:string|null,error:string|null}>, errors:string[]}>}
 */
export async function parsePreview({ file = null, text = '', bestEffort = true, verify = true } = {}) {
  const res = await fetch('/api/parse-preview', inputRequest({ file, text, bestEffort, verify }))
  if (!res.ok) throw await jobFailure(res)
  return res.json()
}

/**
 * Submits a batch and gets back the envelope — including `owner_token`, which
 * the server issues EXACTLY ONCE and never again. Lose it and the job can no
 * longer be cancelled or deleted; it only expires. Whoever is merely shown a
 * results URL does not hold it, which is the entire ownership model here (no
 * accounts).
 * @returns {Promise<{job_id:string, molecule_count:number, status:string, owner_token:string}>}
 */
export async function createJob({ file = null, text = '', bestEffort = true, verify = true } = {}) {
  const res = await fetch('/api/jobs', inputRequest({ file, text, bestEffort, verify }))
  if (!res.ok) throw await jobFailure(res)
  return res.json()
}

/**
 * @returns {Promise<{job_id:string, status:string, total:number, done:number, failed:number, created_at:number, expires_at:number}>}
 */
export async function fetchJobStatus(jobId) {
  const res = await fetch(`/api/jobs/${encodeURIComponent(jobId)}`)
  if (!res.ok) throw await jobFailure(res, jobId)
  return res.json()
}

/**
 * One page of rows. Paginate against `retrievable`, not `total`: `total` is
 * what was submitted, `retrievable` is what can actually be read back, and on
 * a failed job the second is short of the first. The server caps `limit` at
 * 1000.
 * @returns {Promise<{job_id:string, offset:number, limit:number, total:number, retrievable:number, rows:Array<object>}>}
 */
export async function fetchJobResults(
  jobId,
  { offset = 0, limit = 50, sort = 'index', order = 'asc' } = {}
) {
  // `sort` and `order` are sent always, not only when non-default, so the
  // server's own default can never silently disagree with this one.
  const query = new URLSearchParams({
    offset: String(offset),
    limit: String(limit),
    sort,
    order,
  })
  const res = await fetch(`/api/jobs/${encodeURIComponent(jobId)}/results?${query}`)
  if (!res.ok) throw await jobFailure(res, jobId)
  return res.json()
}

/**
 * The CSV link, as a URL rather than a fetch: the browser downloads it, so it
 * never passes through JS memory (a 10,000-row file is the point of the
 * endpoint). It is rate limited far more tightly than polling is — a human
 * downloads their results once or twice, not sixty times a minute.
 */
export function jobResultsCsvUrl(jobId) {
  return `/api/jobs/${encodeURIComponent(jobId)}/results.csv`
}

/**
 * Stops a running job. Cooperative on the server: it marks the job cancelled
 * and the workers decline the next chunk, so molecules already in flight
 * still finish. Requires the owner token.
 */
export async function cancelJob(jobId, ownerToken) {
  const query = new URLSearchParams({ owner_token: ownerToken ?? '' })
  const res = await fetch(`/api/jobs/${encodeURIComponent(jobId)}/cancel?${query}`, {
    method: 'POST',
  })
  if (!res.ok) throw await jobFailure(res, jobId)
  return res.json()
}

/**
 * Discards a finished job's results. Requires the owner token. The server
 * answers 409 for a job that is still running — cancel it first — and that
 * sentence is worth showing verbatim.
 */
export async function deleteJob(jobId, ownerToken) {
  const query = new URLSearchParams({ owner_token: ownerToken ?? '' })
  const res = await fetch(`/api/jobs/${encodeURIComponent(jobId)}?${query}`, {
    method: 'DELETE',
  })
  if (!res.ok) throw await jobFailure(res, jobId)
  return res.json().catch(() => ({}))
}

/**
 * Draws one molecule, on demand. This is why batch rows carry no image: an
 * SVG per row would make a 5,000-row job tens of megabytes in Redis, so the
 * picture is fetched for the row someone actually looks at. A molecule that
 * cannot be drawn is a normal 2xx with `error` set, not a rejection.
 * @returns {Promise<{depiction_svg:string|null, error:string|null}>}
 */
export async function depictMolecule(smiles) {
  const res = await fetch(`/api/depict?smiles=${encodeURIComponent(smiles)}`)
  if (!res.ok) throw await jobFailure(res)
  return res.json()
}
