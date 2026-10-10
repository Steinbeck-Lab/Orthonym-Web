import { useEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { checkHealth } from '../lib/api'
import { GITHUB_URL, NEW_ISSUE_URL } from '../lib/github'
import { KINDS, buildIssue, isComplete, issueUrl, kindById } from '../lib/issueForm'
import BuddyDrawing from './BuddyDrawing'
import CopyButton from './CopyButton'
import Icon from './Icon'

// The Issues tab's dialog: Kekunyo asks whether to be guided or to start from
// GitHub's blank form, and the guided path ends on GitHub's new-issue page
// with the title, text and label filled in. The visitor submits it there,
// under their own account; nothing here sends anything anywhere until they
// press the final link. The questions and the issue text are lib/issueForm.js.
//
// A native <dialog> opened with showModal(): the browser supplies the focus
// trap, Escape, the inert page behind it and the ::backdrop. Desktop only,
// because the tab is (IssueBuddy.jsx); the phone menu still links GitHub's
// blank form directly (owner decision 2026-10-10).

const STEPS = ['start', 'kind', 'details', 'review']

// Kekunyo's face per step: waving hello, listening while you type, delighted
// once the issue is written. The moods are CSS only (`.issue-dialog__buddy`).
const MOOD = { start: 'wave', kind: 'listen', details: 'listen', review: 'happy' }

export default function IssueDialog({ open, onClose }) {
  const dialogRef = useRef(null)
  const headingRef = useRef(null)
  const { pathname } = useLocation()
  const [step, setStep] = useState('start')
  const [back, setBack] = useState(false)
  const [kindId, setKindId] = useState(null)
  const [answers, setAnswers] = useState({})
  const [engine, setEngine] = useState(null)

  useEffect(() => {
    const dialog = dialogRef.current
    if (open && !dialog.open) {
      // A reopened dialog starts at the top, but keeps the draft: closing it
      // by accident must not cost someone what they typed.
      setStep('start')
      setBack(false)
      dialog.showModal()
      checkHealth().then(setEngine, () => setEngine(null))
    } else if (!open && dialog.open) {
      dialog.close()
    }
  }, [open])

  // Each step's heading takes focus so a screen reader announces where it is.
  useEffect(() => {
    if (open) headingRef.current?.focus()
  }, [step, open])

  const kind = kindById(kindId)
  const issue = kind && buildIssue(kind, answers, {
    page: pathname,
    engineVersion: engine?.engine_version,
    engineCommit: engine?.engine_commit,
  })
  const url = issue && issueUrl(GITHUB_URL, issue)
  const index = STEPS.indexOf(step)

  function go(next) {
    setBack(STEPS.indexOf(next) < index)
    setStep(next)
  }

  function pickKind(id) {
    setKindId(id)
    go('details')
  }

  return (
    <dialog
      ref={dialogRef}
      className="issue-dialog"
      aria-labelledby="issue-dialog-title"
      onClose={onClose}
      // A click on the dialog element itself is a click on the backdrop.
      onClick={(event) => event.target === event.currentTarget && onClose()}
    >
      <div className="issue-dialog__card">
        <span className="issue-dialog__buddy" data-mood={MOOD[step]} aria-hidden="true">
          <BuddyDrawing />
        </span>

        <header className="issue-dialog__head">
          <ol className="issue-dialog__rail" aria-hidden="true">
            {STEPS.map((s, i) => (
              <li key={s} className={i <= index ? 'is-done' : undefined} />
            ))}
          </ol>
          <button type="button" className="issue-dialog__close" onClick={onClose} aria-label="Close">
            <Icon name="close" size={18} />
          </button>
        </header>

        <div key={step} className={`issue-dialog__step${back ? ' issue-dialog__step--back' : ''}`}>
          <p className="issue-dialog__count">
            Step {index + 1} of {STEPS.length}
          </p>

          {step === 'start' && (
            <>
              <h2 id="issue-dialog-title" ref={headingRef} tabIndex={-1} className="issue-dialog__title">
                Found a problem?
              </h2>
              <p className="issue-dialog__lede">
                Answer a few short questions and the issue is written for you, or start from a blank page on
                GitHub.
              </p>
              <div className="issue-dialog__choices issue-dialog__choices--two">
                <button type="button" className="issue-choice issue-choice--lead" onClick={() => go('kind')}>
                  <span className="issue-choice__icon"><Icon name="pen" size={20} /></span>
                  <span className="issue-choice__label">Guide me</span>
                  <span className="issue-choice__hint">Pick what happened, add the details, check the result.</span>
                </button>
                <a
                  className="issue-choice"
                  href={NEW_ISSUE_URL}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={onClose}
                >
                  <span className="issue-choice__icon"><Icon name="external" size={20} /></span>
                  <span className="issue-choice__label">Blank issue</span>
                  <span className="issue-choice__hint">GitHub&rsquo;s empty form, in a new tab.</span>
                </a>
              </div>
            </>
          )}

          {step === 'kind' && (
            <>
              <h2 id="issue-dialog-title" ref={headingRef} tabIndex={-1} className="issue-dialog__title">
                What happened?
              </h2>
              <div className="issue-dialog__choices">
                {KINDS.map((k) => (
                  <button
                    type="button"
                    key={k.id}
                    className={`issue-choice issue-choice--row${k.id === kindId ? ' is-picked' : ''}`}
                    onClick={() => pickKind(k.id)}
                  >
                    <span className="issue-choice__icon"><Icon name={k.icon} size={18} /></span>
                    <span className="issue-choice__label">{k.label}</span>
                    <span className="issue-choice__hint">{k.hint}</span>
                  </button>
                ))}
              </div>
              <div className="issue-dialog__actions">
                <button type="button" className="btn btn--sm" onClick={() => go('start')}>
                  <Icon name="back" size={13} /> Back
                </button>
              </div>
            </>
          )}

          {step === 'details' && kind && (
            <form
              className="issue-dialog__form"
              onSubmit={(event) => {
                event.preventDefault()
                if (isComplete(kind, answers)) go('review')
              }}
            >
              <h2 id="issue-dialog-title" ref={headingRef} tabIndex={-1} className="issue-dialog__title">
                {kind.label}
              </h2>
              {kind.fields.map((f) => {
                const Control = f.multiline ? 'textarea' : 'input'
                return (
                  <label key={f.key} className="field">
                    <span className="field__label">
                      {f.label}
                      {f.key === kind.need && <span className="issue-dialog__need"> · needed</span>}
                    </span>
                    <Control
                      className={`field__control${f.mono ? '' : ' issue-dialog__prose'}`}
                      value={answers[f.key] ?? ''}
                      placeholder={f.placeholder}
                      required={f.key === kind.need}
                      rows={f.multiline ? 3 : undefined}
                      spellCheck={!f.mono}
                      onChange={(event) => setAnswers((a) => ({ ...a, [f.key]: event.target.value }))}
                    />
                  </label>
                )
              })}
              <div className="issue-dialog__actions">
                <button type="button" className="btn btn--sm" onClick={() => go('kind')}>
                  <Icon name="back" size={13} /> Back
                </button>
                <button type="submit" className="btn btn--sm btn--accent" disabled={!isComplete(kind, answers)}>
                  Check the issue <Icon name="forward" size={13} />
                </button>
              </div>
            </form>
          )}

          {step === 'review' && issue && (
            <>
              <h2 id="issue-dialog-title" ref={headingRef} tabIndex={-1} className="issue-dialog__title">
                Here is your issue
              </h2>
              <figure className="issue-preview">
                <figcaption className="issue-preview__title">{issue.title}</figcaption>
                <pre className="issue-preview__body">{issue.body}</pre>
                <span className="issue-preview__label">{issue.labels}</span>
              </figure>
              <p className="issue-dialog__lede">
                {url
                  ? 'GitHub opens in a new tab with this filled in. Read it, then press Submit there. Issues are public, so leave out anything private.'
                  : 'This is too long to fit in a link. Copy it, then paste it into a blank issue on GitHub.'}
              </p>
              <div className="issue-dialog__actions">
                <button type="button" className="btn btn--sm" onClick={() => go('details')}>
                  <Icon name="back" size={13} /> Edit
                </button>
                {!url && <CopyButton text={`${issue.title}\n\n${issue.body}`} label="Copy the issue" />}
                <a
                  className="btn btn--sm btn--accent"
                  href={url ?? NEW_ISSUE_URL}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={onClose}
                >
                  {url ? 'Open on GitHub' : 'Open a blank issue'} <Icon name="external" size={13} />
                </a>
              </div>
            </>
          )}
        </div>
      </div>
    </dialog>
  )
}
