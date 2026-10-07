// Matomo page counting: which pages are visited, and nothing about what is
// typed into them. Off unless BOTH build args are set (frontend/Dockerfile),
// so a fork, a dev server and `node --test` load no tracker at all, and the
// Privacy page keeps its "no analytics" sentence for them (Privacy.jsx § 5
// reads MATOMO to choose).
//
// Three things the stock Matomo snippet does that this deliberately does not:
//
//   * No cookies. `disableCookies` is the first command, before the tracker
//     URL, so no _pk_* cookie is ever written and Privacy.jsx § 4 ("this site
//     sets no cookies") stays true. The cost is that a returning visitor counts
//     as new.
//   * No link tracking. `enableLinkTracking` reports every outbound click WITH
//     its full address, and the "Report SMILES on GitHub" link (lib/github.js)
//     carries the visitor's SMILES in that address. Enabling it would send
//     submitted structures to the analytics server, which Privacy.jsx § 5 says
//     never happens. Not an oversight; do not add it back.
//   * No query string and no fragment. Only origin + path is reported, so
//     whatever a visitor arrives with after `?` or `#` stays out of it.
//   * No device details. disableBrowserFeatureDetection stops the screen
//     size, the plugin flags and the browser's client hints, and
//     disablePerformanceTracking the page-load timings. Measured with them on:
//     the request then carries the page, the referrer, the title and the local
//     time of day, plus Matomo's own counters (Privacy.jsx § 2 lists them).

// Facts about the Matomo SERVER, not this code, which Privacy.jsx § 2 states
// to visitors. Read them in Matomo under Administration > Privacy > Anonymize
// data. Until BOTH are recorded here no tracker loads, whatever the build args
// say, so the page can never describe a server set-up nobody confirmed.
//   ipBytesMasked   how many trailing bytes of an IPv4 address it removes
//                   before storing (0 = stored in full)
//   rawDataMonths   after how many months it deletes raw visit data
export const MATOMO_SERVER = {
  host: 'matomo.nfdi4chem.de',
  operator: 'Friedrich-Schiller-Universität Jena', // the owner, 2026-10-07; resolves to the university's own proxy
  ipBytesMasked: null,
  rawDataMonths: null,
}

/** True once both server facts are recorded as whole numbers. */
export function serverFactsKnown({ ipBytesMasked, rawDataMonths }) {
  return Number.isInteger(ipBytesMasked) && ipBytesMasked >= 0 && ipBytesMasked <= 3
    && Number.isInteger(rawDataMonths) && rawDataMonths >= 1
}

/** The two build args, resolved: null (off) unless the URL is http(s) or
 *  protocol-relative and the site id is a number. Exported so a test can
 *  reach the empty strings an unset build arg produces. */
export function resolveMatomo(rawUrl, rawSiteId) {
  const url = (rawUrl || '').trim()
  const siteId = String(rawSiteId ?? '').trim()
  if (!/^\d+$/.test(siteId)) return null
  const absolute = url.startsWith('//') ? `https:${url}` : url
  if (!/^https?:\/\/[^/\s]+/.test(absolute)) return null
  return { url: absolute.endsWith('/') ? absolute : `${absolute}/`, siteId }
}

// `import.meta.env?.` because node --test has no import.meta.env at all; vite
// still replaces the whole expression at build time.
export const MATOMO = serverFactsKnown(MATOMO_SERVER)
  ? resolveMatomo(import.meta.env?.VITE_MATOMO_URL, import.meta.env?.VITE_MATOMO_SITE_ID)
  : null

/** What is reported as the page address: origin and path, nothing after. */
export function pageUrl(loc) {
  return `${loc.origin}${loc.pathname}`
}

/** The tracker's set-up, once per page load. disableCookies comes first. */
export function setupCommands({ url, siteId }) {
  return [['disableCookies'], ['disableBrowserFeatureDetection'], ['disablePerformanceTracking'],
    ['setTrackerUrl', `${url}matomo.php`], ['setSiteId', siteId]]
}

/** One page view. `previous` is the last page counted in this tab, sent as the
 *  referrer for an in-app navigation; the first view keeps the browser's. */
export function pageViewCommands(url, title, previous) {
  return [...(previous ? [['setReferrerUrl', previous]] : []), ['setCustomUrl', url], ['setDocumentTitle', title], ['trackPageView']]
}
