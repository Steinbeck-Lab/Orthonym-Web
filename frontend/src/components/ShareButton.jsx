import { useEffect, useRef, useState } from 'react'
import { canShare, shareUrl } from '../lib/shareLink'
import Icon from './Icon'

/**
 * Copies a share link to this structure (lib/shareLink.js). The link carries
 * the input only, not the Translate switches, so the person who opens it gets
 * the tier their own switches produce -- hence "names this structure", not
 * "this result". A small glass chip
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

  // A structure too large to fit a readable link gets no chip, rather than
  // one that copies a link opening an empty page.
  if (!canShare(fields)) return null

  return (
    <button
      type="button"
      className={`share-chip${copied ? ' share-chip--done' : ''}`}
      onClick={copy}
      aria-label="Copy a link that names this structure"
      title="Copy link"
    >
      <Icon name={copied ? 'check' : 'link'} size={14} />
    </button>
  )
}
