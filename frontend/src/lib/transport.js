// What a failed request means, in the reader's terms.
//
// Home and /explain used to say "Could not reach Orthonym's backend" for
// EVERY non-2xx answer, because the fetch helpers threw away the status: a
// 503 (no worker has a live JVM), a 429 (the rate limit working as designed)
// and a 413 (input too large) all told the visitor the server was down.
// /from-name already told them apart (IupacToSmiles.jsx TransportNotice); the
// 503 sentence here is that page's wording, so every surface describes the
// same backend state the same way.

/** A rejected fetch as an Error carrying `status`, and the backend's own
 *  `detail` as the message when the body has one (FastAPI's HTTPException
 *  shape). */
export async function httpError(res, what) {
  let detail = null
  try {
    const body = await res.json()
    if (typeof body?.detail === 'string') detail = body.detail
  } catch {
    // Not JSON: the status still says what happened.
  }
  const err = new Error(detail || `${what} failed with ${res.status}`)
  err.status = res.status
  return err
}

/** The sentence for an HTTP failure, or null when the backend itself did not
 *  answer (the caller then says it could not reach the backend). That is a
 *  missing status (fetch threw) OR a 502: the page talks to the backend
 *  through a same-origin proxy (Vite in dev, nginx in production), and a
 *  backend that is down comes back as the proxy's 502, never as a fetch
 *  error. The backend itself sends no 502. */
export function transportMessage(error) {
  const status = error?.status
  if (!status || status === 502) return null
  if (status === 429) return 'Orthonym’s request limit was hit. Wait a minute, then try again.'
  if (status === 503) {
    return 'Orthonym’s backend is up, but no worker has a live JVM. Naming endpoints answer 503 until a worker reports one.'
  }
  if (status === 504) return 'This took too long rather than failed. Try again in a moment.'
  if (status === 413) return `Orthonym refused this input as too large (${error.message}).`
  return `Orthonym’s backend answered with an error (${status}). Try again in a moment.`
}
