import { NAMED_STATUSES, stateLabelFor } from '../lib/statuses'
import TierLamp from './TierLamp'
import { roundtripLine } from '../lib/explainVerdict'

/**
 * The confidence tier and its round-trip proof, for one named result.
 *
 * Extracted from Tile so /explain can show a tier without a second copy of
 * this grammar. It is not decoration: PRODUCT.md principle 3 requires the
 * PIN-vs-fallback-vs-best-effort status wherever a name appears, and
 * DESIGN.md encodes it as a monochrome rule beneath the name with a specific
 * meaning per style. Two copies of that would drift, and a drifted copy
 * misstates how confident the engine actually is.
 *
 * /api/explain does NOT return a tier, so a page that only decomposes a name
 * has nothing to render here -- that is why this takes a whole result row and
 * returns null without one, rather than being handed loose fields.
 *
 * ONE VOICE, not two. This used to take a `level` prop and carry two
 * spellings of the same verdict: a plain-English one for /explain's Learn
 * mode and a terse technical one for Expert. The switch that chose between
 * them is gone (owner instruction: the setting was confusing), and the two
 * spellings are merged rather than one of them deleted. The sentence says in
 * plain words what the check DID -- a reader new to this needs that more than
 * an expert does, not less -- and still prints the round-trip SMILES itself,
 * because PRODUCT.md principle 1 says determinism is proven, not asserted,
 * and the proof is the string.
 *
 * The WORDS themselves live in `lib/explainVerdict.js` rather than here, and
 * that is not tidiness: `npm test` runs bare `node --test`, which cannot
 * import a file containing JSX, so a sentence written inline in this
 * component is a sentence no test in the repo can reach. This one states how
 * confident the engine is, so it is worth proving.
 */
export default function ConfidenceReport({ row }) {
  if (!row || !NAMED_STATUSES.has(row.status)) return null
  const line = roundtripLine(row)

  return (
    <div className="confidence-report">
      {/* Inside the label, for the reason Tile.jsx records: nested, the lamp
          flows with the words whatever the parent's display is. */}
      <span className="tile__state-label">
        <TierLamp status={row.status} />
        {stateLabelFor(row)}
      </span>
      {line && (
        <p className="tile__roundtrip">
          {line.lead}{' '}
          <span
            className={
              line.available
                ? `tile__roundtrip-result${line.match ? '' : ' tile__roundtrip-result--mismatch'}`
                : 'tile__roundtrip-result tile__roundtrip-result--unavailable'
            }
          >
            {line.result}
          </span>
          {/* The proof, when there is one: the SMILES OPSIN read the name back
              into. Absent only when the check could not run, in which case
              `line.tail` says so instead -- a tier whose rule claims a
              round-trip must never fall silent about a missing one. */}
          {line.smiles && <> <code className="tile__roundtrip-smiles">{line.smiles}</code></>}
          {line.tail && <> {line.tail}</>}
        </p>
      )}
    </div>
  )
}
