import { useEffect, useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'

// The site header: a floating, blurred, rounded bar that sticks to the top —
// ChemAudit's signature shell (github.com/Kohulan/ChemAudit), adapted toward
// STITCH's own world. It keeps STITCH's faces (Saira wordmark, mono nav) and
// uses the one crimson accent for the logo mark and the active route. There
// is deliberately no theme toggle: this build is light-only.
//
// The active route is marked three ways at once, and colour is only one of
// them: aria-current (assistive tech), a crimson text step, and a crimson
// dot + faint pill. Below 960px the seven routes collapse behind a single
// menu button instead of wrapping onto three lines.

const NAV_LINKS = [
  { to: '/', label: 'Translate', end: true },
  { to: '/from-name', label: 'IUPAC → Structure' },
  // One entry where there were three. /structure and /teach were the same
  // capability reached two different ways -- both now redirect here, and the
  // page's own Input tabs (name / SMILES / draw) are what used to be separate
  // routes. See spec section 12.
  { to: '/explain', label: 'Explain' },
  { to: '/health', label: 'Health Check' },
  { to: '/about', label: 'About' },
]

// The naming engine's public source — the same repo the About page links to.
const GITHUB_URL = 'https://github.com/Kohulan/OpenSTOUT'

// A minimal molecule/stitch mark: two nodes joined by a bond, one stroke
// weight, inheriting the crimson accent via currentColor.
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

function GitHubMark() {
  return (
    <svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0016 8c0-4.42-3.58-8-8-8z" />
    </svg>
  )
}

function Navigation() {
  const [open, setOpen] = useState(false)
  const location = useLocation()

  // Close the mobile menu whenever the route changes.
  useEffect(() => {
    setOpen(false)
  }, [location.pathname])

  // Close on Escape.
  useEffect(() => {
    if (!open) return
    function onKey(event) {
      if (event.key === 'Escape') setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  return (
    <header className="site-head">
      <div className="site-head__inner">
        <div className="site-head__bar">
          <NavLink to="/" end className="brand" aria-label="STITCH — home">
            <BrandMark />
            <span className="brand__word">Stitch</span>
          </NavLink>

          <nav className="site-nav" aria-label="Main">
            {NAV_LINKS.map((link) => (
              <NavLink
                key={link.to}
                to={link.to}
                end={link.end}
                className={({ isActive }) =>
                  isActive ? 'site-nav__link site-nav__link--active' : 'site-nav__link'
                }
              >
                {link.label}
              </NavLink>
            ))}
          </nav>

          <div className="site-head__aux">
            <span className="site-head__divider" aria-hidden="true" />
            <a
              className="site-head__ext"
              href={GITHUB_URL}
              target="_blank"
              rel="noopener noreferrer"
            >
              <GitHubMark />
              GitHub
            </a>
          </div>

          <button
            type="button"
            className="site-nav__toggle"
            aria-label={open ? 'Close menu' : 'Open menu'}
            aria-expanded={open}
            onClick={() => setOpen((v) => !v)}
          >
            {open ? (
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
                <line x1="6" y1="6" x2="18" y2="18" />
                <line x1="18" y1="6" x2="6" y2="18" />
              </svg>
            ) : (
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
                <line x1="3" y1="7" x2="21" y2="7" />
                <line x1="3" y1="12" x2="21" y2="12" />
                <line x1="3" y1="17" x2="21" y2="17" />
              </svg>
            )}
          </button>
        </div>

        {open && (
          <nav className="site-nav__mobile" aria-label="Main">
            {NAV_LINKS.map((link) => (
              <NavLink
                key={link.to}
                to={link.to}
                end={link.end}
                className={({ isActive }) =>
                  isActive ? 'site-nav__mlink site-nav__mlink--active' : 'site-nav__mlink'
                }
              >
                {link.label}
              </NavLink>
            ))}
            <span className="site-nav__mobile-sep" aria-hidden="true" />
            <a
              className="site-nav__mlink"
              href={GITHUB_URL}
              target="_blank"
              rel="noopener noreferrer"
            >
              <GitHubMark />
              GitHub
            </a>
          </nav>
        )}
      </div>
    </header>
  )
}

export default Navigation
