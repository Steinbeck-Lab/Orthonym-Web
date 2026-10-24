import { canShare, shareUrl } from '../lib/shareLink'
import CopyButton from './CopyButton'

/**
 * A link that names this structure (lib/shareLink.js), as a glass chip beside
 * the name's copy button. "This structure", not "this result": the link
 * carries the input, not the Translate switches, so whoever opens it gets the
 * tier their own switches give. No chip when the link would be too long to
 * read back, rather than one that opens an empty page.
 */
export default function ShareButton({ fields }) {
  if (!canShare(fields)) return null
  return (
    <CopyButton
      text={shareUrl(fields)}
      label="Copy a link that names this structure"
      icon="link"
      className="share-chip"
    />
  )
}
