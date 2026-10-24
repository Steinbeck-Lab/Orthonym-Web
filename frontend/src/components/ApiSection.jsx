import endpoints from '../lib/apiEndpoints.json'
import useHealth from '../lib/useHealth'
import CopyButton from './CopyButton'

// Every public endpoint, one curl each. The list is one JSON file that
// backend/tests/test_api_docs.py checks against the real routes, both ways.
// The limits are this server's own, from /api/health; until it answers they
// are left out rather than shown as numbers nobody measured.
const LIMIT_LINES = [
  ['fast_per_minute', (n) => `${n} naming requests per minute`],
  ['fast_path_max_molecules', (n) => `${n} structures per naming request`],
  ['jobs_per_hour', (n) => `${n} batch jobs per hour`],
  ['max_concurrent_jobs', (n) => `${n} batch jobs running at once`],
  ['max_batch_size', (n) => `${n.toLocaleString('en')} molecules per job`],
  ['max_file_size_mb', (n) => `${n} MB per upload`],
  ['download_per_minute', (n) => `${n} downloads per minute`],
]

export default function ApiSection() {
  const limits = useHealth()?.limits

  return (
    <section className="api card" id="api" aria-labelledby="api-title">
      <div className="about-section__head">
        <h2 className="about-section__title" id="api-title">
          Use the API
        </h2>
        <p className="about-section__note">
          Everything the site does, you can call. No key; the limits are per IP address. A 429
          answer means wait a minute and try again.
        </p>
      </div>

      {limits && (
        <ul className="api__limits" role="list" aria-label="Limits on this server">
          {LIMIT_LINES.map(([key, line]) => (
            <li key={key}>{line(limits[key])}</li>
          ))}
        </ul>
      )}

      <ul className="api__list" role="list">
        {endpoints.map((e) => (
          <li className="api__row" key={`${e.method} ${e.path}`}>
            <h3 className="api__name">
              <span className="api__method">{e.method}</span> <code>{e.path}</code>
            </h3>
            <p className="api__summary">{e.summary}</p>
            <div className="api__example">
              <pre className="about-code" tabIndex={0} aria-label={`Example call for ${e.path}`}>
                {e.curl}
              </pre>
              <CopyButton text={e.curl} label={`Copy the ${e.method} ${e.path} example`} />
            </div>
          </li>
        ))}
      </ul>
    </section>
  )
}
