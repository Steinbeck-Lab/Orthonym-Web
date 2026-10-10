import { useState } from 'react'
import { NEW_ISSUE_URL } from '../lib/github'
import BuddyDrawing from './BuddyDrawing'
import IssueDialog from './IssueDialog'

// The issue tab: a crimson tab on the left edge of every page, and Kekunyo,
// the buddy that waits behind it. Pointing at the tab, or reaching it with the
// keyboard, brings the buddy out: it glides from behind the tab, its face
// lights up, and a bubble asks for the issue. The drawing is BuddyDrawing.jsx.
//
// Pressing it opens IssueDialog: a guided form that ends on GitHub's
// new-issue page already filled in, or GitHub's blank form (owner request
// 2026-10-10). It used to be a plain link to that blank form.
//
// Desktop only. Below 960px, where the header folds into its menu, a fixed
// edge tab would sit on the page, so the blank-form link lives in the menu
// instead (Navigation.jsx). The CSS is `.issue-buddy` and `.issue-dialog` in
// App.css.
//
// Everything inside the button but its label is aria-hidden: the label says
// what it does, and the bubble repeats it for sighted visitors only.
// Renders nothing when the deployment has no GitHub repository.

export default function IssueBuddy() {
  const [open, setOpen] = useState(false)
  if (!NEW_ISSUE_URL) return null
  return (
    <>
      <button
        type="button"
        className="issue-buddy"
        onClick={() => setOpen(true)}
        aria-haspopup="dialog"
        aria-label="Report an issue"
      >
        <span className="issue-buddy__tab" aria-hidden="true">
          <svg viewBox="0 0 16 16" focusable="false">
            <circle cx="8" cy="8" r="6.2" fill="none" stroke="currentColor" strokeWidth="1.6" />
            <circle cx="8" cy="8" r="1.7" fill="currentColor" />
          </svg>
          <span className="issue-buddy__word">Issues</span>
        </span>
        <span className="issue-buddy__actor" aria-hidden="true">
          <BuddyDrawing />
        </span>
        <span className="issue-buddy__bubble" aria-hidden="true">
          <b>Found a problem?</b>
          Tell us about it.
          <small>Guided or blank</small>
        </span>
      </button>
      <IssueDialog open={open} onClose={() => setOpen(false)} />
    </>
  )
}
