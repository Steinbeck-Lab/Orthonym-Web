import { GITHUB_URL, reportIssueUrl } from '../lib/github'
import Icon from './Icon'

// Said BEFORE the click, because the click itself is the disclosure: the
// SMILES rides in the github.com address, so GitHub has it the moment the tab
// opens, whether or not the visitor then submits. Privacy.jsx § 5 says the
// same in full.
//
// The LABEL carries the warning ("SMILES", "GitHub"), not only the tooltip:
// `title` shows on mouse hover and never on a tap or keyboard focus (owner
// decision 2026-09-25). The tooltip adds the rest, and a screen reader reads
// it once, as the link's description. No sr-only copy: it read the warning a
// second time, in capitals, and an absolutely-positioned span with no
// positioned ancestor widened the page at 320px.
const WARNING =
  'Opens github.com in a new tab with this SMILES filled in. If you submit the issue, other people can read it.'

/**
 * "Report SMILES on GitHub" for a result Orthonym could not name. Renders
 * nothing for any other result, or when the deployment has no GitHub
 * repository.
 *
 * @param row    the result row, as the page already holds it.
 * @param where  the page, in words, for the issue body ("Home", "Explain").
 * @param settings  {bestEffort, verify} the row was named with, when known.
 */
export default function ReportLink({ row, where, settings }) {
  const href = reportIssueUrl(GITHUB_URL, row, where, settings)
  if (!href) return null
  return (
    <a className="report-link" href={href} target="_blank" rel="noopener noreferrer" title={WARNING}>
      Report SMILES on GitHub
      <Icon name="external" size={12} />
    </a>
  )
}
