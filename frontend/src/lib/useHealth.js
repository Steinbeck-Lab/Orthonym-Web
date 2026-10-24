import { useEffect, useState } from 'react'
import { healthOnce } from './api'

/** /api/health, asked once per page load: null while asking, false when
 *  nothing answered, else the payload. */
export default function useHealth() {
  const [health, setHealth] = useState(null)
  useEffect(() => {
    let live = true
    healthOnce()
      .then((h) => live && setHealth(h))
      .catch(() => live && setHealth(false))
    return () => {
      live = false
    }
  }, [])
  return health
}
