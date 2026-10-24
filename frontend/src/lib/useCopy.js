import { useEffect, useRef, useState } from 'react'

/**
 * Copy `text` to the clipboard: [copied, copy]. `copied` is true for `ms`
 * after a copy that worked; `copy()` resolves true or false. A blocked
 * clipboard (insecure context, denied permission) claims nothing.
 */
export default function useCopy(text, ms = 1400) {
  const [copied, setCopied] = useState(false)
  const timer = useRef(null)

  useEffect(() => () => clearTimeout(timer.current), [])

  async function copy() {
    try {
      await navigator.clipboard.writeText(text)
    } catch {
      return false
    }
    setCopied(true)
    clearTimeout(timer.current)
    timer.current = setTimeout(() => setCopied(false), ms)
    return true
  }

  return [copied, copy]
}
