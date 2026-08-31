import { Link } from 'react-router-dom'

// Site-wide footer — appears once, beneath every page, via the router shell.
// A restrained take on ChemAudit's footer: its structure (brand block, link
// columns, a credit line) kept, but flat and quiet in Orthonym's world — no
// giant background wordmark, no aurora, no marquee. The one warmth is the
// crimson keyline at the top edge (in App.css) and the crimson heart below.

const GITHUB_URL = 'https://github.com/Kohulan/Orthonym'

function BrandMark() {
  return (
    <svg
      className="brand__mark"
      viewBox="0 0 32 32"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.4"
      strokeLinecap="round"
      aria-hidden="true"
    >
      <line x1="11" y1="21" x2="21" y2="11" />
      <circle cx="8" cy="24" r="3.5" fill="currentColor" stroke="none" />
      <circle cx="24" cy="8" r="3.5" fill="currentColor" stroke="none" />
    </svg>
  )
}

function Footer() {
  const year = 2026 // build year; the app has no clock and must not invent one

  return (
    <footer className="site-footer">
      <div className="site-footer__inner page-shell">
        <div className="site-footer__brand">
          <span className="brand">
            <BrandMark />
            <span className="brand__word">Orthonym</span>
          </span>
          <p className="site-footer__tagline">
            A deterministic, rule-based SMILES&nbsp;&rarr;&nbsp;IUPAC name translator. It shows its
            engine&rsquo;s real output only &mdash; verified PINs, honest fallbacks, and honest
            abstains.
          </p>
        </div>

        <nav className="site-footer__col" aria-label="Tools">
          <span className="site-footer__col-title">Tools</span>
          <Link className="site-footer__link" to="/">
            Translate
          </Link>
          <Link className="site-footer__link" to="/structure">
            Structure &rarr; IUPAC
          </Link>
          <Link className="site-footer__link" to="/from-name">
            IUPAC &rarr; Structure
          </Link>
          <Link className="site-footer__link" to="/explain">
            Explain
          </Link>
        </nav>

        <nav className="site-footer__col" aria-label="More">
          <span className="site-footer__col-title">More</span>
          <Link className="site-footer__link" to="/teach">
            Learn
          </Link>
          <Link className="site-footer__link" to="/health">
            Health Check
          </Link>
          <Link className="site-footer__link" to="/about">
            About
          </Link>
          <a
            className="site-footer__link"
            href={GITHUB_URL}
            target="_blank"
            rel="noopener noreferrer"
          >
            GitHub
          </a>
        </nav>
      </div>

      <div className="site-footer__base page-shell">
        <span className="site-footer__copy">&copy; {year} Orthonym &middot; MIT License</span>
        <span className="site-footer__credit">
          Made with{' '}
          <svg
            className="site-footer__coffee"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <path d="M4 9h13v5a4 4 0 0 1-4 4H8a4 4 0 0 1-4-4V9z" />
            <path d="M17 10h2.4a2.5 2.5 0 0 1 0 5H17" />
            <path d="M8 2.5c-.6 1 .6 2 0 3" />
            <path d="M12 2.5c-.6 1 .6 2 0 3" />
          </svg>
          <span className="sr-only"> coffee </span> by{' '}
          <a href="https://github.com/Kohulan" target="_blank" rel="noopener noreferrer">
            Kohulan&nbsp;R.
          </a>
        </span>
      </div>
    </footer>
  )
}

export default Footer
