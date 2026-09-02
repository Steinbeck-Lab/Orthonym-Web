// Site-wide footer — appears once, beneath every page, via the router shell.
//
// Three parts and nothing else: copyright + the rights-holder mark, a credit
// pill, a back-to-top button. It replaced a brand block plus two columns of
// link duplicates — every one of which already sits in the header nav, two of
// which (/structure, /teach) had just become redirects, so the footer was
// carrying stale copies of a list it did not own.
//
// There is no footer BAND: the whole strip is transparent and only the credit
// pill and the round back-to-top button lift off the grey ground, matching
// ChemAudit's footer (user instruction: "I don't need a whole white bar at the
// bottom, use pill style similar to chemaudit"). Restoring a background here
// re-creates the bar that was removed on purpose.
//
// The crimson is the coffee cup and nothing else, which keeps the one-accent
// rule DESIGN.md sets: accent lives in chrome, never on a confidence tier.

// A coffee cup, inline rather than an asset: one glyph, no network request,
// no file to lose, and it inherits currentColor so the accent rule holds
// wherever the footer is themed.
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
      {/* steam */}
      <path d="M9 2.5c-.6.8-.6 1.6 0 2.4M12.5 2c-.7.9-.7 1.9 0 2.9M16 2.5c-.6.8-.6 1.6 0 2.4" />
      {/* cup */}
      <path d="M3.5 8h14v5.5a5 5 0 0 1-5 5h-4a5 5 0 0 1-5-5V8Z" />
      {/* handle */}
      <path d="M17.5 9.5h1.6a2.4 2.4 0 0 1 0 4.8h-1.6" />
    </svg>
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
        <p className="site-footer__copyright">
          <span>&copy; {year} Orthonym. All rights reserved.</span>
          {/* The rights holder named by its mark, as bchemxtractweb's footer
              does. Two notes carried over from that implementation, both
              measured there and still true of this artwork:
                - The wordmark's caps are a QUARTER of the artwork's height,
                  so 2rem is the floor at which the lettering stays readable;
                  do not shrink it to match the 0.7rem mono beside it.
                - The SVG's own viewBox is "0 48 876 202" -- already tightened
                  to its ink, so no gap opens after the copyright text. The
                  artwork itself is untouched.
              Its crimson is BRAND artwork, not the chrome accent, so the
              one-accent rule is unaffected (DESIGN.md records this). */}
          <a
            className="site-footer__org"
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
        </p>

        <p className="credit">
          <span className="credit__lead">Made with</span>
          <CoffeeMark />
          <span className="credit__lead">by</span>
          <a
            className="credit__who"
            href="https://github.com/Kohulan"
            target="_blank"
            rel="noopener noreferrer"
          >
            Kohulan.R
          </a>
          <span className="credit__lead">at</span>
          <span className="credit__where">
            Beilstein-Institut <span className="credit__x">&times;</span> Steinbeck-Lab
          </span>
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
