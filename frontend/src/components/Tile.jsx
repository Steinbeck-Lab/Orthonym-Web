import ThreadedName from './ThreadedName'

const STATE_LABEL = {
  pin: 'Preferred IUPAC Name (PIN)',
  fallback: 'Not a verified PIN',
  best_effort: 'Unverified best-effort name — could not round-trip check this',
  abstain: 'Could not confidently name this',
  error: null, // uses the literal API error message instead
}

// API status values use underscores (e.g. "best_effort"); CSS state
// classes use hyphens (e.g. "tile--best-effort") per the existing
// tile--pin / tile--fallback / tile--abstain / tile--error naming.
const STATE_CLASS = {
  pin: 'pin',
  fallback: 'fallback',
  best_effort: 'best-effort',
  abstain: 'abstain',
  error: 'error',
}

// Statuses that ship a real (if not always verified) name -- these three
// share the same "name-block + supporting depiction" layout, distinguished
// only by border/fill treatment per state (see Home.css).
const NAMED_STATUSES = new Set(['pin', 'fallback', 'best_effort'])

/**
 * One cell of the sampler grid.
 *
 * phase: 'pending' (queued, result not yet revealed) | 'active' (currently
 *        being sewn into place) | 'done' (settled, final state)
 */
export default function Tile({ row, phase, reduceMotion }) {
  const { smiles, status, name, tier, formula, error, depiction_svg, roundtrip_smiles, roundtrip_match } = row
  const isPending = phase === 'pending'
  const isActive = phase === 'active'
  const animateName = isActive && !reduceMotion

  const stateClass = isPending ? 'pending' : STATE_CLASS[status] || status
  const label = isPending
    ? 'Resolving'
    : status === 'error'
      ? error || 'Could not parse this SMILES string'
      : STATE_LABEL[status]

  return (
    <li
      className={`tile tile--${stateClass}${isActive ? ' tile--active' : ''}`}
      aria-busy={isActive || isPending}
    >
      <div className="tile__head">
        <code className="tile__smiles" title={smiles}>
          {smiles}
        </code>
        {!isPending && tier && <span className="tile__tier">{tier}</span>}
      </div>

      <div className="tile__patch">
        {isPending && (
          <div className="tile__pending-cloth" aria-hidden="true">
            <span className="tile__pending-dash" />
            <span className="tile__pending-dash" />
            <span className="tile__pending-dash" />
          </div>
        )}

        {!isPending && NAMED_STATUSES.has(status) && (
          <div className="tile__result-row">
            <div className={`tile__name-block tile__name-block--${STATE_CLASS[status]}`}>
              <ThreadedName name={name} animate={animateName} />
            </div>
            {depiction_svg && (
              <div className="tile__depiction">
                <img src={depiction_svg} alt={`2D structure depiction for "${name}"`} />
              </div>
            )}
          </div>
        )}

        {!isPending && status === 'abstain' && (
          <div className="tile__name-block tile__name-block--abstain" aria-hidden="true">
            <span className="tile__weave" />
          </div>
        )}

        {!isPending && status === 'error' && (
          <div className="tile__name-block tile__name-block--error" aria-hidden="true">
            <span className="tile__snip tile__snip--a" />
            <span className="tile__snip tile__snip--b" />
          </div>
        )}
      </div>

      <div className="tile__foot">
        <span className="tile__state-label">{label}</span>
        {!isPending && roundtrip_smiles && (
          <p className="tile__roundtrip">
            round-trip check: <code className="tile__roundtrip-smiles">{roundtrip_smiles}</code>{' '}
            <span
              className={`tile__roundtrip-result${roundtrip_match ? '' : ' tile__roundtrip-result--mismatch'}`}
            >
              {roundtrip_match ? '— matches ✓' : '— does not match ✗'}
            </span>
          </p>
        )}
        {!isPending && status === 'abstain' && formula && (
          <span className="tile__formula">Formula: {formula}</span>
        )}
      </div>
    </li>
  )
}
