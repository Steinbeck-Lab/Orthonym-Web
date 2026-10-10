// THIS SITE's source on GitHub, and the "Report SMILES on GitHub" link built
// from it.
//
// Moved here out of Navigation.jsx so the header link and the report link
// read ONE value: a deployment that turns the header link off must not keep a
// report link pointing at the same repository.
//
// THIS SITE's source, and only this site's.
//
// The distinction matters, because this link used to mean something else and
// was correctly switched off for it. It pointed at the naming ENGINE,
// whose repository was private then and answered 404 to an anonymous
// visitor -- a dead link in the header of every route. It points at
// Orthonym-Web, this web app; About and Terms link the engine
// (github.com/Steinbeck-Lab/Orthonym) where they credit it.
//
// Still overridable: a fork or a private deployment sets VITE_GITHUB_URL and
// gets its own source. The literal `none` ships no link and no separator.
//
// `||`, not `??`, and the default is repeated in frontend/Dockerfile on
// purpose. An unset build arg reaches vite as an EMPTY STRING, not as
// undefined, so `??` would keep the empty string and silently ship no link --
// which is exactly the bug this line replaced. `||` treats empty as absent,
// and `none` is then the explicit way to say "off".
const GITHUB_URL_DEFAULT = 'https://github.com/Steinbeck-Lab/Orthonym-Web'

/** The build arg, resolved. Exported so a test can reach '' and 'none',
 *  which node --test (no import.meta.env) never produces on its own. */
export function resolveGithubUrl(raw) {
  const url = raw || GITHUB_URL_DEFAULT
  return url === 'none' ? null : url
}

// `import.meta.env?.` because node --test has no import.meta.env at all; vite
// still replaces the whole expression at build time.
export const GITHUB_URL = resolveGithubUrl(import.meta.env?.VITE_GITHUB_URL)

/** GitHub's blank new-issue form for `repo`, or null when there is no repo.
 *  The issue tab (IssueBuddy.jsx) and the phone menu open it; unlike
 *  reportIssueUrl it carries nothing from the page. */
export function newIssueUrl(repo) {
  return repo ? `${repo.replace(/\/+$/, '')}/issues/new` : null
}

export const NEW_ISSUE_URL = newIssueUrl(GITHUB_URL)

// The error rows that are the ENGINE's failure, not the visitor's input. The
// backend marks them (tasks.py): `engine_error` when naming raised,
// `timeout` when a batch chunk ran out of time. Every other error row is a
// SMILES that could not be read, and a report of a typo is noise.
//
// A timeout row carries its SMILES only for the one molecule that was running
// when the limit fired; the rest of the chunk never reached the engine, has
// no SMILES, and so is not reportable either.
const ENGINE_FAILURES = new Set(['engine_error', 'timeout'])

// An abstain the visitor's own switches produced: best-effort off, and no
// round trip to verify the name the engine DID find (orthonym_service.py).
const WITHHELD = 'withheld_unchecked'

// GitHub refuses a new-issue address much past 8 KB. The backend caps a typed
// SMILES at 2000 characters, which fits; an SDF record has no cap.
const MAX_URL_LENGTH = 8000

// What a result is called in the issue. Plain words, not the status code.
const OUTCOME = {
  abstain: 'no name (abstain)',
  error: 'the engine failed',
}

// Keeps the title readable; the full SMILES is in the body.
const TITLE_SMILES_MAX = 60

// A switch the issue can state, or nothing when the page does not know it (a
// batch job created before the backend recorded its settings).
function switchLine(label, value) {
  return typeof value === 'boolean' && `- ${label}: ${value ? 'on' : 'off'}`
}

/** True when a result is one Orthonym could not name and the visitor could
 *  usefully report: an abstain, or a crash / timeout. Never a bad SMILES. */
export function isReportable(row) {
  if (!row?.smiles) return false
  if (row.status === 'abstain') return row.limit_code !== WITHHELD
  return row.status === 'error' && ENGINE_FAILURES.has(row.limit_code)
}

/**
 * The github.com "new issue" address, pre-filled with this result, or null
 * when there is nothing to report or nowhere to report it.
 *
 * Carries the SMILES and what the engine said about it, and NOTHING else from
 * the row. In particular not `input` or `input_id`: a batch line's ID token
 * is the visitor's own label for the compound and may be confidential, and a
 * job id or owner token would make Privacy.jsx § 4 false.
 *
 * @param repo   the repository URL (GITHUB_URL). Anything that is not a
 *               github.com repository gets no link: `/issues/new` means
 *               nothing on another host.
 * @param row    a result row (ResultItem or BatchRow shape).
 * @param where  the page the visitor was on, in words, e.g. "Home".
 * @param settings  {bestEffort, verify} the result was named WITH -- not the
 *               switches' current position. Best-effort off abstains on
 *               molecules the defaults name, so a report that omits it cannot
 *               be reproduced.
 */
export function reportIssueUrl(repo, row, where, settings) {
  // ponytail: github.com only. A GitHub Enterprise fork gets no report link
  // until someone needs one; widen this check then.
  if (!repo?.startsWith('https://github.com/') || !isReportable(row)) return null
  const { smiles, status, limit_code, formula, error, engine_version, engine_commit } = row
  const short = smiles.length > TITLE_SMILES_MAX ? `${smiles.slice(0, TITLE_SMILES_MAX)}…` : smiles
  const facts = [
    `- Result: ${OUTCOME[status]}`,
    limit_code && `- Reason code: \`${limit_code}\``,
    formula && `- Formula: ${formula}`,
    error && `- Message: ${error}`,
    // The engine tracks main: without its version a report cannot be replayed.
    engine_version && `- Engine: v${engine_version}${engine_commit ? ` (${engine_commit.slice(0, 7)})` : ''}`,
    where && `- Page: ${where}`,
    switchLine('Best-effort mode', settings?.bestEffort),
    switchLine('OPSIN verify', settings?.verify),
  ].filter(Boolean)
  const body = [
    'Orthonym could not name this molecule.',
    '',
    '**SMILES**',
    '',
    '```',
    smiles,
    '```',
    '',
    ...facts,
    '',
    '<!-- Anything else that helps: the name you expected, where the structure comes from. -->',
  ].join('\n')
  const query = new URLSearchParams({ title: `Could not name: ${short}`, body, labels: 'bug' })
  const url = `${newIssueUrl(repo)}?${query}`
  // ponytail: a structure too big for the address gets no link rather than a
  // truncated SMILES nobody can reproduce. A paste-it-yourself body is the
  // upgrade if giant SDF records ever need reporting.
  return url.length <= MAX_URL_LENGTH ? url : null
}
