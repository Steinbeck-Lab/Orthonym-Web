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
 * `level` changes the WORDS, never the verdict. Learn mode may not name a tool
 * or a format (teach-mode spec section 5: no OPSIN, no SMILES, no "parser"),
 * but it still has to show the proof -- PRODUCT.md principle 1 says
 * determinism must be provable, not asserted, and a reader who is new to this
 * needs that more than an expert does, not less. So Learn says what the check
 * DID and drops the machinery, rather than dropping the check.
 */
export default function ConfidenceReport({ row, level = 'expert' }) {
  if (!row || !NAMED_STATUSES.has(row.status)) return null
  const { status, roundtrip_smiles, roundtrip_match } = row

  return (
    <div className="confidence-report">
      <span className="tile__state-label">{STATE_LABEL[status]}</span>
      {roundtrip_smiles && level === 'learn' && (
        <p className="tile__roundtrip">
          We read this name back to see which molecule it describes.{' '}
          <span
            className={`tile__roundtrip-result${roundtrip_match ? '' : ' tile__roundtrip-result--mismatch'}`}
          >
            {roundtrip_match
              ? 'It gives back the same molecule ✓'
              : 'It gives back a different molecule ✗'}
          </span>
        </p>
      )}
      {roundtrip_smiles && level !== 'learn' && (
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
      {!roundtrip_smiles && VERIFIED_STATUSES.has(status) && (
        <p className="tile__roundtrip">
          {level === 'learn' ? (
            <>
              We could not read this name back to double-check it, so we cannot promise it
              is right.
            </>
          ) : (
            <>
              round-trip check:{' '}
              <span className="tile__roundtrip-result tile__roundtrip-result--unavailable">
                unavailable
              </span>{' '}
              — could not confirm this result
            </>
          )}
        </p>
      )}
    </div>
  )
}
