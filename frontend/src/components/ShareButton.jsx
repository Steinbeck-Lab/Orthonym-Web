import { useEffect, useRef, useState } from 'react'
import { shareUrl } from '../lib/shareLink'
import Icon from './Icon'

/**
 * Copies a share link to this result (lib/shareLink.js). A small glass chip
 * that sits beside the name's own copy button, so both copy actions live in
 * one place; a sheen crosses it on hover, like the site's large buttons.
 *
 * Like CopyButton, the label stays constant for assistive tech and only the
 * aria-hidden icon flips to a check.
 */
export default function ShareButton({ fields }) {
  const [copied, setCopied] = useState(false)
  const timer = useRef(null)

  useEffect(() => () => clearTimeout(timer.current), [])

  async function copy() {
    try {
      await navigator.clipboard.writeText(shareUrl(fields))
      setCopied(true)
      clearTimeout(timer.current)
      timer.current = setTimeout(() => setCopied(false), 1400)
    } catch {
      // Clipboard blocked: leave the icon alone rather than claim a copy.
    }
  }

  return (
    <button
      type="button"
      className={`share-chip${copied ? ' share-chip--done' : ''}`}
      onClick={copy}
      aria-label="Copy link to this result"
      title="Copy link"
    >
      <Icon name={copied ? 'check' : 'link'} size={14} />
    </button>
  )
}
