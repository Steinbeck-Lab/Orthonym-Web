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

// The mark between the two labs. It was a typed multiplication sign; it is now
// two crimson strokes that SEW THEMSELVES on hover, staggered, one after the
// other -- a stitch, on a site called STITCH, at the exact point where two
// institutions are joined. That is the whole joke and the whole reason it is
// allowed to move: it says something true about the thing it sits inside.
//
// Rules it keeps: crimson lives in chrome, and a footer is chrome (DESIGN.md's
// One-Accent Rule; it never touches a confidence tier). It is aria-hidden with
// an sr-only "and" beside it, so the pill still reads as a sentence. It runs
// only on hover of the whole pill, in 420 ms on the project's standard
// ease-out-expo, and prefers-reduced-motion switches it off -- delight that
// blocks or nags is not delight.
function StitchCross() {
  return (
    <svg
      className="credit__x"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      aria-hidden="true"
    >
      {/* Each stroke is 12.73 units long (9-9-root-2), which is why the CSS
          dasharray is 13: one dash covers the whole path exactly once. */}
      <path className="credit__x-stroke" d="M3.5 3.5 12.5 12.5" />
      <path className="credit__x-stroke" d="M12.5 3.5 3.5 12.5" />
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
          &copy; {year} STITCH. All rights reserved.
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
          <StitchCross />
          <span className="credit__where">Steinbeck-Lab</span>
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
