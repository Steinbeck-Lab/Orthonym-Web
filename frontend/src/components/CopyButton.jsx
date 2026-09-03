import { useEffect, useRef, useState } from 'react'
import Icon from './Icon'

/**
 * Copies `text` to the clipboard and flips to a check for a moment so the click
 * has a visible result. Used on the IUPAC name, where a reader's next step is
 * almost always to paste the name somewhere else.
 *
 * The label stays constant for assistive tech ("Copy name"); the icon is the
 * only thing that changes, and it is aria-hidden, so a screen-reader user is
 * not told "copied" on a control they did not just operate.
 */
export default function CopyButton({ text, label = 'Copy name' }) {
  const [copied, setCopied] = useState(false)
  const timer = useRef(null)

  useEffect(() => () => clearTimeout(timer.current), [])

  async function copy() {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      clearTimeout(timer.current)
      timer.current = setTimeout(() => setCopied(false), 1400)
    } catch {
      // Clipboard blocked (insecure context, denied permission). Nothing to do
      // but leave the icon unchanged -- a failed copy must not claim success.
    }
  }

  return (
    <button
      type="button"
      className={`copy-btn${copied ? ' copy-btn--done' : ''}`}
      onClick={copy}
      aria-label={label}
      title={label}
    >
      <Icon name={copied ? 'check' : 'copy'} size={14} />
    </button>
  )
}
