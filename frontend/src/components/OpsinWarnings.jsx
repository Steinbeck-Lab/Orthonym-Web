import { warningLabel } from '../lib/opsinWarnings'

// OPSIN's own warnings, shown as OPSIN wrote them. Not a verdict of this
// page: OPSIN parsed the name and said the reading may not be the only one.
export default function OpsinWarnings({ warnings }) {
  if (!warnings?.length) return null
  return (
    <ul className="opsin-warnings">
      {warnings.map((w) => (
        <li key={w.type + w.message}>
          {warningLabel(w)} <span className="opsin-warnings__detail">{w.message}</span>
        </li>
      ))}
    </ul>
  )
}
