// The guided issue form behind the Issues tab (components/IssueDialog.jsx):
// what each kind of report asks, and how the answers become a GitHub
// new-issue address. Nothing here talks to a server. The address is opened
// in a new tab and the visitor submits the issue on GitHub, under their own
// account, after reading exactly what it says.

import { clipTitle, engineLine } from './github.js'

/**
 * The four kinds of report, in the order the dialog offers them. `fields` drive
 * the details step; `need` is the one field without which the report is
 * useless. `engine: true` adds the engine version line, because a name
 * question cannot be replayed on another engine.
 */
export const KINDS = [
  {
    id: 'wrong-name',
    label: 'A name looks wrong',
    hint: 'Orthonym named a molecule, but not the way you expected.',
    icon: 'spell',
    prefix: 'Wrong name',
    labels: 'bug',
    engine: true,
    need: 'smiles',
    fields: [
      { key: 'smiles', label: 'SMILES', mono: true, placeholder: 'CC(=O)Oc1ccccc1C(=O)O' },
      { key: 'given', label: 'Name Orthonym gave', placeholder: 'Copy it from the result' },
      { key: 'expected', label: 'Name you expected', placeholder: 'And a source, if you have one' },
      { key: 'notes', label: 'Anything else', multiline: true, placeholder: 'Optional' },
    ],
  },
  {
    id: 'cannot-name',
    label: 'It could not name a molecule',
    hint: 'No name came back, or the engine failed.',
    icon: 'ban',
    prefix: 'Could not name',
    labels: 'bug',
    engine: true,
    need: 'smiles',
    fields: [
      { key: 'smiles', label: 'SMILES', mono: true, placeholder: 'The structure you submitted' },
      { key: 'said', label: 'What the result said', placeholder: 'For example "Not named"' },
      { key: 'notes', label: 'Anything else', multiline: true, placeholder: 'Optional' },
    ],
  },
  {
    id: 'site',
    label: 'Something on the site broke',
    hint: 'A page, a button or a download did not work.',
    icon: 'bug',
    prefix: 'Site problem',
    labels: 'bug',
    need: 'happened',
    fields: [
      { key: 'did', label: 'What you did', multiline: true, placeholder: 'Opened Explain, drew benzene, pressed Name it' },
      { key: 'happened', label: 'What happened instead', multiline: true, placeholder: 'The page stayed empty' },
    ],
  },
  {
    id: 'idea',
    label: 'I have an idea',
    hint: 'Something Orthonym could do, or do better.',
    icon: 'idea',
    prefix: 'Idea',
    labels: 'enhancement',
    need: 'summary',
    fields: [
      { key: 'summary', label: 'In one line', placeholder: 'Export names as an SDF' },
      { key: 'details', label: 'Tell us more', multiline: true, placeholder: 'Optional' },
    ],
  },
]

/** True when the kind's one required answer is filled in. */
export function isComplete(kind, answers) {
  return Boolean(kind && answers[kind.need]?.trim())
}

/**
 * The issue a finished form describes.
 * @param kind     an entry of KINDS.
 * @param answers  {fieldKey: string}; blanks are left out.
 * @param context  {page, engineVersion, engineCommit}: where the visitor was
 *                 (a path, never a query string) and the engine that answered.
 * @returns {{title: string, body: string, labels: string}}
 */
export function buildIssue(kind, answers, context = {}) {
  const sections = kind.fields
    .filter((f) => answers[f.key]?.trim())
    .map((f) => {
      const value = answers[f.key].trim()
      return f.mono ? `**${f.label}**\n\n\`\`\`\n${value}\n\`\`\`` : `**${f.label}**\n\n${value}`
    })
  const facts = [
    context.page && `- Page: ${context.page}`,
    kind.engine && engineLine(context.engineVersion, context.engineCommit),
    '- Sent from the issue form on the site',
  ].filter(Boolean)
  return {
    title: `${kind.prefix}: ${clipTitle(answers[kind.need] ?? '')}`,
    body: [...sections, facts.join('\n')].join('\n\n'),
    labels: kind.labels,
  }
}
