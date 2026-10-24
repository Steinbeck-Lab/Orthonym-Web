// Share links carry the input in the URL FRAGMENT (`#smiles=...`), never the
// query. Browsers do not send a fragment to the server, so a shared structure
// stays out of the nginx access log and out of Matomo -- Privacy.jsx says so.
//
// decodeURIComponent, not URLSearchParams: URLSearchParams reads `+` as a
// space, and a hand-typed `#smiles=[NH4+]` must keep its charge.

const MAX_HASH = 4000

/** `{ smiles: 'CCO' }` -> `'#smiles=CCO'`, keys in the order given. */
export function buildShareHash(fields) {
  return (
    '#' +
    Object.entries(fields)
      .map(([key, value]) => `${key}=${encodeURIComponent(value)}`)
      .join('&')
  )
}

/** The fields in a share hash, or null when there are none to use. */
export function readShareHash(hash) {
  if (!hash || hash.length > MAX_HASH) return null
  const fields = {}
  for (const part of hash.replace(/^#/, '').split('&')) {
    const at = part.indexOf('=')
    if (at < 1) continue
    let value
    try {
      value = decodeURIComponent(part.slice(at + 1))
    } catch {
      return null
    }
    if (value) fields[part.slice(0, at)] = value
  }
  return Object.keys(fields).length ? fields : null
}
