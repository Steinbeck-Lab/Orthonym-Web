import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import CreditCross from './CreditCross'
import { healthOnce } from '../lib/api'

// Site-wide footer — appears once, beneath every page, via the router shell.
//
// Three parts and nothing else: copyright + the rights-holder mark, a credit
// pill, a back-to-top button. It replaced a brand block plus two columns of
// link duplicates — every one of which already sits in the header nav, two of
// which (/structure, /teach) had just become redirects, so the footer was
// carrying stale copies of a list it did not own.
//
// The three legal links added on 2026-09-06 are not a fourth part and not a
// return of those columns: they ride ON the copyright line, and they are the
// only routes the header nav does NOT carry, so they are not duplicates of
// anything.
//
// There is no footer BAND: the whole strip is transparent and only the credit
// pill and the round back-to-top button lift off the grey ground, matching
// ChemAudit's footer (user instruction: "I don't need a whole white bar at the
// bottom, use pill style similar to chemaudit"). Restoring a background here
// re-creates the bar that was removed on purpose.
//
// The crimson here is the coffee cup and the three legal links — both on
// DESIGN.md's allowlist (chrome and inline links), neither anywhere near a
// confidence tier, which is the one place the accent may never go. The links
// take `--accent-deep` rather than `--link` because this strip sits on the
// bare ground; App.css carries the measurement.

// A coffee cup, inline rather than an asset: one glyph, no network request,
// no file to lose, and it inherits currentColor so the accent rule holds
// wherever the footer is themed.
//
// Its three wisps of steam RISE when the pill is hovered, each on its own
// beat, and keep going while the pointer stays. At rest they are drawn and
// still, so the glyph reads as coffee whether or not anything animates -- the
// motion is a reward for looking, never the thing that makes it legible.
// prefers-reduced-motion switches it off.
function CoffeeMark() {
  return (
    <svg
      className="credit__cup"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {/* Steam, as three separate paths rather than one three-subpath path,
          because each wisp rises on its own beat -- see .credit__steam. */}
      <path className="credit__steam" d="M9 2.5c-.6.8-.6 1.6 0 2.4" />
      <path className="credit__steam" d="M12.5 2c-.7.9-.7 1.9 0 2.9" />
      <path className="credit__steam" d="M16 2.5c-.6.8-.6 1.6 0 2.4" />
      {/* cup */}
      <path d="M3.5 8h14v5.5a5 5 0 0 1-5 5h-4a5 5 0 0 1-5-5V8Z" />
      {/* handle */}
      <path d="M17.5 9.5h1.6a2.4 2.4 0 0 1 0 4.8h-1.6" />
    </svg>
  )
}

// Which engine names here, read once from /api/health. The lamp says whether
// naming works right now; the words say it too, so the hue is never the only
// signal. The commit rides behind the version and slides out on hover/focus.
function EngineChip() {
  const [health, setHealth] = useState(null) // null = asking, false = no answer

  useEffect(() => {
    let live = true
    healthOnce()
      .then((h) => live && setHealth(h))
      .catch(() => live && setHealth(false))
    return () => { live = false }
  }, [])

  const version = health?.engine_version
  const commit = health?.engine_commit?.slice(0, 7)
  const asking = health === null
  const up = health?.status === 'OK'
  const repo = 'https://github.com/Steinbeck-Lab/Orthonym'
  // The aria-label replaces the chip's text for assistive technology, so the
  // per-character spans below are never read one letter at a time.
  const label = asking ? 'Engine: checking'
    : !version ? 'Engine offline'
    : [`Engine version ${version}`, commit && `commit ${commit}`, !up && 'offline'].filter(Boolean).join(', ')

  return (
    <a
      className={`engine-chip engine-chip--${asking ? 'asking' : up ? 'live' : 'down'}`}
      href={commit ? `${repo}/commit/${health.engine_commit}` : repo}
      target="_blank"
      rel="noopener noreferrer"
      aria-label={label}
    >
      <span className="engine-chip__lamp" />
      <span>Engine</span>
      {version && (
        <span className="engine-chip__ver">
          {[...`v${version}`].map((c, i) => (
            <span key={i} style={{ '--i': i }}>{c}</span>
          ))}
        </span>
      )}
      {asking && <span>···</span>}
      {commit && (
        <span className="engine-chip__commit">
          <span>· {commit}</span>
        </span>
      )}
      {!asking && !up && <span>{version ? '· offline' : 'offline'}</span>}
    </a>
  )
}

function Footer() {
  // Build year, not new Date(): the app has no clock of its own and must not
  // invent one. Bump it deliberately.
  const year = 2026

  function scrollToTop() {
    // 'smooth' unless the visitor asked for less motion. prefers-reduced-motion
    // is a stated accessibility requirement here (WCAG 2.2 AA), not a nicety,
    // and this is the one place in the footer that animates.
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    window.scrollTo({ top: 0, behavior: reduce ? 'auto' : 'smooth' })
  }

  return (
    <footer className="site-footer">
      <div className="site-footer__inner page-shell">
        {/* The three legal routes ride ON the copyright line rather than
            becoming a fourth object in the grid above. Two reasons, both
            recorded rather than aesthetic:
              - the grid is `1fr auto auto` by owner instruction 2026-09-03,
                and a fourth track would move the credit pill off the right
                edge that instruction put it on.
              - the footer's deleted link columns (see the block comment at
                the top of this file) were deleted because every link in them
                already sat in the header nav. These three do NOT sit in the
                header nav -- the notch carries the five route labels only --
                so they are not the duplicates that deletion was about.
            They are `<Link>`, not `<a>`: an `<a href>` inside the router
            shell reloads the whole app for an in-app route. */}
        <div className="site-footer__meta">
          <p className="site-footer__copyright">
            &copy; {year} Orthonym. All rights reserved.
            <span className="site-footer__legal">
              <Link to="/imprint">Impressum</Link>
              <Link to="/privacy">Privacy</Link>
              <Link to="/terms">Terms</Link>
            </span>
          </p>
          <EngineChip />
        </div>

        <p className="credit">
          <span className="credit__lead">Made with</span>
          <CoffeeMark />
          <span className="credit__lead">by</span>
          <a
            className="credit__who"
            href="https://kohulanr.com"
            target="_blank"
            rel="noopener noreferrer"
          >
            Kohulan.R
          </a>
          <span className="credit__lead">at</span>
          {/* The rights holder named by its mark rather than by its name, as
              bchemxtractweb's footer does. Two notes carried over from that
              implementation, both measured there and still true of this
              artwork:
                - The wordmark's caps are a QUARTER of the artwork's height,
                  so 2rem is the floor at which the lettering stays readable.
                  It is deliberately taller than the 0.82rem text beside it;
                  shrinking it to match the line would make it decoration.
                - The SVG's own viewBox is "0 48 876 202" -- already tightened
                  to its ink, so no gap opens on either side. Artwork
                  untouched.
              Its crimson is BRAND artwork, not the chrome accent, so the
              one-accent rule is unaffected (DESIGN.md records this). */}
          <a
            className="credit__org"
            href="https://www.beilstein-institut.de/en/"
            target="_blank"
            rel="noopener noreferrer"
          >
            <img
              src="/Logo_Beilstein_schmal_RGB.svg"
              alt="Beilstein-Institut"
              width={876}
              height={202}
            />
          </a>
          <span className="sr-only">and</span>
          <CreditCross />
          <a
            className="credit__where"
            href="https://cheminf.uni-jena.de"
            target="_blank"
            rel="noreferrer"
          >
            Steinbeck-Lab
          </a>
        </p>

        <button
          type="button"
          className="to-top"
          onClick={scrollToTop}
          aria-label="Back to top"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M12 19V5M5 12l7-7 7 7" />
          </svg>
        </button>
      </div>
    </footer>
  )
}

export default Footer
