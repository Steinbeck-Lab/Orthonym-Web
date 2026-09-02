import { NAMED_STATUSES, STATE_CLASS, STATE_LABEL, VERIFIED_STATUSES } from '../lib/statuses'
import ThreadedName from './ThreadedName'

/**
 * One cell of the sampler grid.
 *
 * phase: 'pending' (queued, result not yet revealed) | 'active' (currently
 *        resolving into place) | 'done' (settled, final state)
 */
export default function Tile({ row, phase, index = 0, reduceMotion }) {
  const { smiles, status, name, formula, error, depiction_svg, roundtrip_smiles, roundtrip_match } = row
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
      /* --i staggers the card's own arrival. The cards used to appear with no
         transition at all, which read as a jolt next to the name resolving
         inside them. */
      style={{ '--i': index }}
    >
      <div className="tile__head">
        <code className="tile__smiles" title={smiles}>
          {smiles}
        </code>
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
        {/* This tier's rule (double/dashed) claims an OPSIN round-trip
            confirmed the name, but no proof came back with this result.
            The proof must never go missing silently -- an absent line here
            would look identical to a tier that carries no such claim. */}
        {!isPending && !roundtrip_smiles && VERIFIED_STATUSES.has(status) && (
          <p className="tile__roundtrip">
            round-trip check:{' '}
            <span className="tile__roundtrip-result tile__roundtrip-result--unavailable">
              unavailable
            </span>{' '}
            — could not confirm this result
          </p>
        )}
        {/* The link back to the control that produced this tier. An
            unverified name exists only because best-effort mode is on, and
            without saying so the tier reads as a property of the molecule
            rather than a consequence of a switch the reader can turn off.
            The switch's own hint states the forward direction; this is the
            reverse, in the one place it matters.
            Not a "check again" button: the round trip already ran, and the
            engine is deterministic, so a retry returns the same answer. */}
        {!isPending && status === 'best_effort' && (
          <span className="tile__origin">
            Shown because best-effort mode is on. Turn it off for a verified name or an
            honest abstain.
          </span>
        )}
        {!isPending && status === 'abstain' && formula && (
          <span className="tile__formula">Formula: {formula}</span>
        )}
      </div>
    </li>
  )
}
