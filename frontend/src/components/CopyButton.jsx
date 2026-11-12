import { useEffect, useRef, useState } from 'react'
import useCopy from '../lib/useCopy'
import Icon from './Icon'

/**
 * Copies `text` to the clipboard and flips to a check for a moment so the click
 * has a visible result. Used on the IUPAC name, where a reader's next step is
 * almost always to paste the name somewhere else.
 *
 * `label` is the button's accessible name and stays constant, so a table full
 * of these can say WHICH value each one copies ("Copy SMILES"). The outcome is
 * said separately, in one polite status beside the button: "Copied" or "Copy
 * failed". A blocked clipboard (useCopy resolves false) used to show nothing
 * at all; it now shows a warning mark and says so.
 */
export default function CopyButton({ text, label = 'Copy name', icon = 'copy', className = '' }) {
  const [copied, copy] = useCopy(text)
  const [failed, setFailed] = useState(false)
  const timer = useRef(null)

  useEffect(() => () => clearTimeout(timer.current), [])

  async function handleClick() {
    const ok = await copy()
    clearTimeout(timer.current)
    setFailed(!ok)
    if (!ok) timer.current = setTimeout(() => setFailed(false), 2400)
  }

  const outcome = copied ? 'Copied' : failed ? 'Copy failed' : ''

  return (
    <>
      <button
        type="button"
        className={`copy-btn ${className}${copied ? ' copy-btn--done' : ''}`}
        onClick={handleClick}
        aria-label={label}
        title={outcome || label}
      >
        <Icon name={copied ? 'check' : failed ? 'warn' : icon} size={14} />
      </button>
      {/* Always mounted, so the first outcome is announced; .sr-only is
          absolutely positioned, so it adds no gap to a flex row. */}
      <span className="sr-only" role="status">
        {outcome}
      </span>
    </>
  )
}
