import { NAMED_STATUSES, STATE_CLASS, STATE_LABEL, VERIFIED_STATUSES } from '../lib/statuses'
import useDepiction from '../lib/useDepiction'
import CopyButton from './CopyButton'
import ThreadedName from './ThreadedName'
import { ChemFormula } from './Typeset'

/**
 * One cell of the sampler grid.
 *
 * phase: 'pending' (queued, result not yet revealed) | 'active' (currently
 *        resolving into place) | 'done' (settled, final state)
 */
export default function Tile({ row, phase, index = 0, reduceMotion }) {
  const { smiles, status, name, formula, error, depiction_svg, roundtrip_smiles, roundtrip_match } = row
  // The RETRANSLATED structure: what OPSIN parsed the name back to. The naming
  // result only ships the INPUT's picture, so this one is drawn on demand from
  // roundtrip_smiles. A null roundtrip (no round trip ran) is a no-op fetch.
  const retrans = useDepiction(roundtrip_smiles)
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
      {/* THE NAME LEADS the card (owner instruction 2026-09-03: title bold,
          larger, at the top), with the copy button inline at the end of it and
          the PIN/round-trip verdict in olive directly beneath -- the proof sits
          with the claim rather than in the foot. */}
      {!isPending && NAMED_STATUSES.has(status) && (
        <div className={`tile__name-block tile__name-block--${STATE_CLASS[status]}`}>
          <span className="tile__name-line">
            <ThreadedName name={name} animate={animateName} />
            <CopyButton text={name} />
          </span>
        </div>
      )}

      {!isPending && NAMED_STATUSES.has(status) && (
        <div className="tile__verify">
          <span className="tile__verify-label">{label}</span>
          {roundtrip_smiles ? (
            <span className="tile__verify-rt">
              round-trip check: <code>{roundtrip_smiles}</code>{' '}
              {roundtrip_match ? '— matches ✓' : '— does not match ✗'}
            </span>
          ) : (
            VERIFIED_STATUSES.has(status) && (
              <span className="tile__verify-rt">
                round-trip check: unavailable — could not confirm this result
              </span>
            )
          )}
        </div>
      )}

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

        {/* Input structure and the retranslated one, side by side, so the
            round-trip claim is something the eye can check. The second panel
            only appears when a round trip actually ran. */}
        {!isPending && NAMED_STATUSES.has(status) && depiction_svg && (
          <div className="tile__depictions">
            <figure className="tile__depiction">
              <img src={depiction_svg} alt={`2D structure you entered, "${smiles}"`} />
              <figcaption className="tile__depiction-cap">Input</figcaption>
            </figure>
            {roundtrip_smiles && (
              <figure className="tile__depiction">
                {retrans.svg ? (
                  <img src={retrans.svg} alt={`2D structure OPSIN re-parsed from the name, "${roundtrip_smiles}"`} />
                ) : (
                  <span className="tile__depiction-note">
                    {retrans.loading ? 'Drawing…' : 'No picture'}
                  </span>
                )}
                <figcaption className="tile__depiction-cap">
                  Re-parsed {roundtrip_match ? '✓' : '✗'}
                </figcaption>
              </figure>
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

      {/* The foot renders only when it has something to say. A verified PIN or
          fallback moved its label and proof up into the olive verdict, leaving
          the foot empty -- and an empty foot still drew its top hairline and
          padding, which was the whitespace at the card's bottom edge. */}
      {(isPending ||
        !NAMED_STATUSES.has(status) ||
        status === 'best_effort' ||
        (status === 'abstain' && formula)) && (
      <div className="tile__foot">
        {/* The state label lives with the name (in the olive verdict) for a
            named result; the foot carries it only for the states that have no
            name to sit under -- pending, abstain, error. */}
        {(isPending || !NAMED_STATUSES.has(status)) && (
          <span className="tile__state-label">{label}</span>
        )}
        {/* The link back to the control that produced this tier. Without it
            the tier reads as a property of the MOLECULE rather than a
            consequence of a switch the reader can turn off. The switch's own
            hint states the forward direction; this is the reverse, in the one
            place it matters.

            TWO switches can produce a best-effort row now, and they need
            different sentences -- naming the wrong one sends the reader to a
            control that will not do what the sentence promises. The row itself
            says which: a genuine best-effort name (the escalated namer
            produced it) still HAD its round trip run, so it carries a
            roundtrip_smiles. A null one means no round trip ran at all, which
            is the OPSIN-verify switch being off -- or OPSIN being unreachable,
            which is why the sentence says what did not happen rather than
            asserting which switch it was.

            Derived from the ROW, deliberately, not from the live switch
            position passed down as a prop: this tile may be from an earlier
            submission, or served from cache, and the switch may have been
            flipped since. The row's own data is the truth about the row.

            Not a "check again" button either: the engine is deterministic, so
            a retry returns the same answer. */}
        {!isPending && status === 'best_effort' && (
          <span className="tile__origin">
            {roundtrip_smiles
              ? 'Shown because best-effort mode is on. Turn it off for a verified name or an honest abstain.'
              : 'No round-trip check ran, so nothing confirmed this name. Turn OPSIN verify on to check it.'}
          </span>
        )}
        {!isPending && status === 'abstain' && formula && (
          <span className="tile__formula">
            Formula: <ChemFormula formula={formula} />
          </span>
        )}
      </div>
      )}
    </li>
  )
}
