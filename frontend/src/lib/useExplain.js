import { useRef, useState } from 'react'
import { explainMolecule, explainName, translateBatch } from './api'
import { explainPhase } from './explainView'

// The switches the tier row is fetched with -- Home's defaults, since /explain
// has no switches of its own. Named once so the request and the report link
// cannot state different settings.
export const TIER_SETTINGS = { bestEffort: true, verify: true }

/**
 * One explanation: the fetch, its tier row and its stale-reply guard, moved
 * out of Explain.jsx unchanged so /compare can run two side by side.
 *
 * phase: 'idle' | 'loading' | 'success' | 'error' (mirrors IupacToSmiles.jsx)
 * run(value, mode): mode is 'name' or 'smiles' (a drawing is a structure once
 * Ketcher has given its SMILES).
 */
export default function useExplain() {
  const [phase, setPhase] = useState('idle')
  const [data, setData] = useState(null)
  const [apiError, setApiError] = useState(null)
  const [fetchError, setFetchError] = useState(null)
  // The confidence tier for a molecule Orthonym itself named. /api/explain does
  // not return one, so it comes from /api/translate alongside. Null in 'name'
  // mode on purpose: the user supplied the name, so there is no Orthonym
  // verdict on it to report.
  const [tierRow, setTierRow] = useState(null)
  // The mode the DISPLAYED result was fetched with, not the tab currently
  // selected: the tier disclosure must not rewrite its verdict when the tab
  // changes after a result has landed (PRODUCT.md principle 3).
  const [resultMode, setResultMode] = useState(null)
  // What the displayed result was asked for, as share-link fields: `name` for
  // a typed name, `smiles` for a typed or drawn structure.
  const [shareFields, setShareFields] = useState(null)
  // Which run is current. The tier fetch settles on its own clock, after the
  // explain request has already released the form, so a reply from an
  // EARLIER molecule could land after the next submit and pin its tier -- and
  // its "Report SMILES on GitHub" link -- under the new result.
  const latestRun = useRef(0)

  function run(value, requestMode) {
    setFetchError(null)
    setPhase('loading')

    const request = requestMode === 'name' ? explainName(value) : explainMolecule(value)

    // A drawn or typed STRUCTURE is something Orthonym names itself, so its
    // confidence tier is a real verdict and PRODUCT.md principle 3 requires it
    // wherever that name appears. /api/explain carries no tier, so fetch it
    // alongside -- in parallel, never blocking the breakdown.
    setTierRow(null)
    setResultMode(requestMode)
    setShareFields(requestMode === 'name' ? { name: value } : { smiles: value })
    const current = ++latestRun.current
    if (requestMode !== 'name') {
      translateBatch([value], TIER_SETTINGS)
        .then((rows) => current === latestRun.current && setTierRow(rows?.[0] ?? null))
        .catch(() => current === latestRun.current && setTierRow(null))
    }

    request
      .then((result) => {
        if (current !== latestRun.current) return
        // A PARTIAL result is a real case: the structure-in path can name and
        // draw a molecule yet fail to decompose the name (TNT's
        // "2,4,6-trinitrotoluene", which OPSIN rejects). Keep the drawing and
        // show the error beside it; only a result with nothing to show is a
        // bare error.
        setApiError(result.error || null)
        if (explainPhase(result) === 'error') {
          setData(null)
          setPhase('error')
        } else {
          setData(result)
          setPhase('success')
        }
      })
      .catch((err) => {
        if (current !== latestRun.current) return
        setFetchError(err ?? new Error('unknown network error'))
        setPhase('idle')
      })
  }

  return { phase, data, apiError, fetchError, tierRow, resultMode, shareFields, run }
}
