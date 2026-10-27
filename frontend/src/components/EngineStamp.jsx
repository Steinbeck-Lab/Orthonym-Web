// Which engine wrote these names, read off the rows themselves (each carries
// engine_version / engine_commit from the worker that named it). The engine
// tracks main, so "the same input, the same name" holds per engine; this line
// is what lets a reader check that. The OPSIN that read each name back rides
// along: the site may run a different one from `pip install orthonym`. More
// than one entry only when a deploy landed between rows.
export default function EngineStamp({ rows }) {
  const engines = [
    ...new Set(
      rows
        .filter((r) => r.engine_version)
        .map((r) => `v${r.engine_version}${r.engine_commit ? ` · ${r.engine_commit.slice(0, 7)}` : ''}${r.opsin_version ? ` with OPSIN ${r.opsin_version}` : ''}`),
    ),
  ]
  if (!engines.length) return null
  return <p className="engine-stamp">Named by Orthonym engine {engines.join(', ')}</p>
}
