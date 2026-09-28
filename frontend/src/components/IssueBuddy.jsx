import { NEW_ISSUE_URL } from '../lib/github'
import BuddyDrawing from './BuddyDrawing'

// The issue tab: a crimson tab on the left edge of every page that opens a
// new issue on this site's GitHub repository, and Kekunyo, the buddy that waits behind
// it. Pointing at the tab, or reaching it with the keyboard, brings the buddy
// out: it glides from behind the tab, its face lights up, and a bubble asks
// for the issue. The drawing is BuddyDrawing.jsx.
//
// Desktop only. Below 960px, where the header folds into its menu, a fixed
// edge tab would sit on the page, so the same link lives in the menu instead
// (Navigation.jsx). The CSS is `.issue-buddy` in App.css.
//
// Everything inside the link but its label is aria-hidden: the label says
// what the link does, and the bubble repeats it for sighted visitors only.
// Renders nothing when the deployment has no GitHub repository.

export default function IssueBuddy() {
  if (!NEW_ISSUE_URL) return null
  return (
    <a
      className="issue-buddy"
      href={NEW_ISSUE_URL}
      target="_blank"
      rel="noopener noreferrer"
      aria-label="Report an issue on GitHub (opens in a new tab)"
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
        Open an issue.
        <small>On GitHub</small>
      </span>
    </a>
  )
}
