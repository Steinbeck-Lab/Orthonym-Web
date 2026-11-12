import Icon from './Icon'
import { warningCopy } from '../lib/opsinWarnings'

// OPSIN's own warnings, shown with OPSIN's words. Not a verdict of this page:
// OPSIN parsed the name and said the reading may not be the only one.
export default function OpsinWarnings({ warnings }) {
  // null (not []) means the backend kept its verdict but could not read
  // OPSIN's warnings (name_check.warnings_or_none): say so rather than imply none.
  if (warnings === null) {
    return (
      <p className="panel-note" role="note">
        OPSIN&rsquo;s warnings could not be read for this name.
      </p>
    )
  }
  if (!warnings?.length) return null
  return (
    <div className="opsin-warnings" role="note">
      {warnings.map((w) => {
        const { title, body } = warningCopy(w)
        return (
          <div className="opsin-warnings__item" key={w.type + w.message}>
            <span className="opsin-warnings__icon" aria-hidden="true">
              <Icon name="warn" />
            </span>
            <p className="opsin-warnings__title">{title}</p>
            <p className="opsin-warnings__body">{body}</p>
            <p className="opsin-warnings__raw">
              <span className="opsin-warnings__raw-label">OPSIN says</span>
              <code>{w.message}</code>
            </p>
          </div>
        )
      })}
    </div>
  )
}
