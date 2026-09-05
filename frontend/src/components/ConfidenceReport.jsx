import { NAMED_STATUSES, STATE_LABEL, VERIFIED_STATUSES } from '../lib/statuses'

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
 */
export default function ConfidenceReport({ row }) {
  if (!row || !NAMED_STATUSES.has(row.status)) return null
  const { status, roundtrip_smiles, roundtrip_match } = row

  return (
    <div className="confidence-report">
      <span className="tile__state-label">{STATE_LABEL[status]}</span>
      {roundtrip_smiles && (
        <p className="tile__roundtrip">
          Round-trip check: we read this name back and it gives{' '}
          <span
            className={`tile__roundtrip-result${roundtrip_match ? '' : ' tile__roundtrip-result--mismatch'}`}
          >
            {roundtrip_match ? 'the same molecule ✓' : 'a different molecule ✗'}
          </span>{' '}
          <code className="tile__roundtrip-smiles">{roundtrip_smiles}</code>
        </p>
      )}
      {/* This tier's rule (double/dashed) claims an OPSIN round-trip
          confirmed the name, but no proof came back with this result.
          The proof must never go missing silently -- an absent line here
          would look identical to a tier that carries no such claim. */}
      {!roundtrip_smiles && VERIFIED_STATUSES.has(status) && (
        <p className="tile__roundtrip">
          Round-trip check:{' '}
          <span className="tile__roundtrip-result tile__roundtrip-result--unavailable">
            unavailable
          </span>{' '}
          — we could not read this name back, so this result is not confirmed.
        </p>
      )}
    </div>
  )
}
