import { useEffect, useState } from 'react'
import { depictMolecule } from './api'

/**
 * Lazily fetch a 2D depiction SVG (data URI) for a SMILES string via
 * GET /api/depict. Used for the RETRANSLATED structure on a result -- the
 * molecule OPSIN re-parsed the name back to -- which the naming result does
 * not carry (only the input's depiction_svg ships with the result; batch rows
 * carry no picture at all, by design).
 *
 * Returns { svg, loading, error }. Passing a falsy `smiles` is a no-op that
 * clears any prior result, so a tile whose round trip did not run simply shows
 * no second panel.
 */
export default function useDepiction(smiles) {
  const [state, setState] = useState({ svg: null, loading: false, error: null })

  useEffect(() => {
    if (!smiles) {
      setState({ svg: null, loading: false, error: null })
      return
    }
    let cancelled = false
    setState({ svg: null, loading: true, error: null })
    depictMolecule(smiles)
      .then((data) => {
        if (cancelled) return
        setState({ svg: data.depiction_svg || null, loading: false, error: data.error || null })
      })
      .catch((err) => {
        if (cancelled) return
        setState({ svg: null, loading: false, error: err.message || 'Could not draw this structure' })
      })
    return () => {
      cancelled = true
    }
  }, [smiles])

  return state
}
