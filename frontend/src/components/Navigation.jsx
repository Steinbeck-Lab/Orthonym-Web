import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { ENGINE_URL, GITHUB_URL, NEW_ISSUE_URL } from '../lib/github'

// The site header: ONE NOTCH ISLAND hanging off the top edge of the window,
// centred, welded to the edge by a pair of concave fillets, so it reads as
// carved out of the top of the page rather than floating over it. It was
// briefly three separate islands; the owner asked for one ("I don't want 3
// notches, move [the wordmark] and github to center, keep single notch").
//
// AT REST it shows the pint mark and the four route labels, and
// nothing else. ON HOVER (or on focus, or on any pointer that cannot hover)
// it GROWS OUTWARD from its centre to reveal the Orthonym wordmark on the left
// and GitHub on the right, each fenced off by a hairline "|". Confirmed with
// the owner before building: the mark stays put at rest, so the site is
// never logo-less, and only the wordmark slides in.
//
// Three details that are load-bearing rather than decorative:
//   * The reveal is CSS only -- max-width plus opacity on the three
//     collapsible parts. Animating a layout property is normally the wrong
//     answer, but the notch must PHYSICALLY grow here, which is a layout
//     change by definition; it is one small flex row, and it is off under
//     prefers-reduced-motion.
//   * The island's gap is ZERO and every gap is a child's own margin. With a
//     flex gap, the collapsed parts would still be separated by it and the
//     resting notch would carry ~80px of dead air.
//   * :focus-within reveals too, and nothing is display:none or
//     visibility:hidden, so a keyboard reaches GitHub -- tabbing to it opens
//     the notch. A touch device (hover: none) simply stays open. That shape
// replaced ChemAudit's floating glass bar on 2026-09-02 at the owner's
// instruction ("use this for header but keep our white and crimson style",
// pointing at an adaptive-notch navigation component). The component itself
// could not be used: it is TSX + Tailwind + framer-motion + lucide-react on a
// codebase that has none of those, and it owns the whole page as a fixed
// full-screen shell. The SHAPE was ported; none of its code was.
//
// Orthonym's own world is otherwise unchanged: the Saira wordmark, the mono
// nav, white cards on the grey ground, the one crimson accent, and no theme
// toggle (this build is light-only).
//
// Since 2026-10-26 the island is onyx lacquer with gold lines, drawn as one
// SVG outline by NotchShape below.
//
// The active route is marked three ways at once, and colour is only one of
// them: aria-current (assistive tech), an ink label, and an ink dot, riding
// a single gold-glaze pill that SLIDES between routes instead of one pill
// per link blinking on and off. Below 960px the four routes collapse
// behind a single menu button instead of wrapping onto three lines.

const NAV_LINKS = [
  { to: '/', label: 'Translate', end: true },
  // "Name", not "IUPAC name": every route on this site is about IUPAC names,
  // so the word carried no information here and made this the longest label in
  // the notch by half. The arrow already says which direction it runs.
  { to: '/from-name', label: 'Name → Structure' },
  // One entry where there were three. /structure and /teach were the same
  // capability reached two different ways -- both now redirect here, and the
  // page's own Input tabs (name / SMILES / draw) are what used to be separate
  // routes. See spec section 12.
  { to: '/explain', label: 'Explain' },
  // Does a claimed name describe a structure? A verdict on structure only.
  { to: '/check', label: 'Check' },
  // Two explanations side by side, the differing parts marked.
  { to: '/compare', label: 'Compare' },
  // Health Check folded into /about as a compact board (Task 18) rather than
  // its own page; /health now redirects there (App.jsx), so the nav no
  // longer needs a separate item. The sliding pill below is measured off the
  // DOM (`measurePill`), never indexed by NAV_LINKS.length, so removing an
  // entry needs no other change here.
  { to: '/about', label: 'About' },
]

// The header's GitHub link. What it points at, and why, is in lib/github.js,
// which the report link on unnamed results reads too.

// The pint from the wordmark, standing in for the O on the home page and for
// the whole name here. Decorative: the link's aria-label already names it.
function BrandMark() {
  return <img className="brand__mark" src="/logos/Orthonym.svg" alt="" aria-hidden="true" />
}

function GitHubMark() {
  return (
    <svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0016 8c0-4.42-3.58-8-8-8z" />
    </svg>
  )
}

// The header island drawn as ONE outline: both fillets, both sides and the
// rounded bottom are a single SVG path, so one glaze, one gold rim and one
// shadow cover the whole notch and no seam can show between three pieces.
// The path is rebuilt from the island's measured size, which changes while
// the notch unfolds on hover.
function NotchShape() {
  const ref = useRef(null)
  const [box, setBox] = useState(null)
  const uid = useId()

  useLayoutEffect(() => {
    const notch = ref.current?.parentElement
    if (!notch) return undefined
    // The two radii are fixed tokens, so they are read once, not per frame.
    const css = getComputedStyle(notch)
    const f = parseFloat(css.getPropertyValue('--notch-wing'))
    const r = parseFloat(css.getPropertyValue('--r-notch'))
    // Fires every frame while the notch unfolds; an unchanged size keeps the
    // same object so React skips the render.
    const measure = () => {
      const w = notch.offsetWidth
      const h = notch.offsetHeight
      setBox((prev) => (prev?.w === w && prev?.h === h ? prev : { w, h, f, r }))
    }
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(notch)
    return () => observer.disconnect()
  }, [])

  if (!box) return <svg ref={ref} className="notch__shape" aria-hidden="true" />

  // The island spans f..x1 in the SVG; a fillet of size f sits each side.
  const { w, h, f, r } = box
  const x1 = f + w
  // Outline without the top edge (the window edge is not part of the rim).
  const rim =
    `M 0 0 A ${f} ${f} 0 0 1 ${f} ${f} L ${f} ${h - r} ` +
    `A ${r} ${r} 0 0 0 ${f + r} ${h} L ${x1 - r} ${h} ` +
    `A ${r} ${r} 0 0 0 ${x1} ${h - r} L ${x1} ${f} A ${f} ${f} 0 0 1 ${x1 + f} 0`
  const body = `${rim} Z`
  // The inner gold line: the bottom and its two corners, d px inside, rising
  // `fade` px up each side as it fades out.
  const d = 3.5
  const fade = 6
  const ri = r - d
  const inlay =
    `M ${f + d} ${h - r - fade} L ${f + d} ${h - r} A ${ri} ${ri} 0 0 0 ${f + r} ${h - d} ` +
    `L ${x1 - r} ${h - d} A ${ri} ${ri} 0 0 0 ${x1 - d} ${h - r} L ${x1 - d} ${h - r - fade}`

  return (
    <svg
      ref={ref}
      className="notch__shape"
      aria-hidden="true"
      width={w + 2 * f}
      height={h}
    >
      <defs>
        {/* --glaze-onyx's stops: an SVG fill cannot take a CSS gradient. */}
        <linearGradient id={`${uid}-glaze`} x1="0" y1="0" x2="0" y2={h} gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="var(--onyx-hi)" />
          <stop offset="0.52" stopColor="var(--onyx)" />
          <stop offset="1" stopColor="var(--onyx-lo)" />
        </linearGradient>
        <linearGradient id={`${uid}-gloss`} x1="0" y1="0" x2="0" y2={h} gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#fff" stopOpacity="0.13" />
          <stop offset="0.46" stopColor="#fff" stopOpacity="0.035" />
          <stop offset="0.465" stopColor="#fff" stopOpacity="0" />
        </linearGradient>
        <linearGradient id={`${uid}-inlay`} x1="0" y1={h - r - fade} x2="0" y2={h - r + fade} gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="var(--gold-hi)" stopOpacity="0" />
          <stop offset="1" stopColor="var(--gold-hi)" stopOpacity="0.8" />
        </linearGradient>
      </defs>
      <path d={body} fill={`url(#${uid}-glaze)`} />
      <path d={body} fill={`url(#${uid}-gloss)`} />
      <path d={rim} fill="none" stroke="var(--gold-bright)" strokeWidth="1.25" />
      <path d={inlay} fill="none" stroke={`url(#${uid}-inlay)`} strokeWidth="1" />
    </svg>
  )
}

function Navigation() {
  const [open, setOpen] = useState(false)
  const location = useLocation()

  // The sliding pill behind the active route. Its geometry has to be
  // MEASURED, not derived: the labels are different widths, the mono face
  // loads late, and the nav re-flows with the viewport. `null` means "no
  // active route in this nav" (an unknown path), in which case no pill is
  // drawn at all rather than a stray 0-width one.
  const navRef = useRef(null)
  const [pill, setPill] = useState(null)
  // The pill must not slide in from the left edge on first paint. It gets its
  // transition one frame AFTER its first real measurement.
  const [slides, setSlides] = useState(false)

  // The one moment a nav can honestly celebrate: arriving somewhere. On a
  // route change the pill slides (below) and the active dot is pulled into a
  // short dash and back -- the same draw-in motif as the footer's joining
  // mark, which makes it a signature rather than a one-off trick. 380ms, and
  // the class is removed afterwards so it can fire again on the next route.
  const [justMoved, setJustMoved] = useState(false)
  const firstRouteRef = useRef(true)

  useEffect(() => {
    // Not on first paint: nobody navigated to arrive here, and an animation
    // that plays on load is decoration rather than feedback.
    if (firstRouteRef.current) {
      firstRouteRef.current = false
      return undefined
    }
    setJustMoved(true)
    const timer = window.setTimeout(() => setJustMoved(false), 420)
    return () => window.clearTimeout(timer)
  }, [location.pathname])

  const measurePill = useCallback(() => {
    const nav = navRef.current
    if (!nav) return
    const active = nav.querySelector('.site-nav__link--active')
    if (!active) {
      setPill(null)
      return
    }
    const navBox = nav.getBoundingClientRect()
    const box = active.getBoundingClientRect()
    setPill({ x: box.left - navBox.left, w: box.width })
  }, [])

  // useLayoutEffect, not useEffect: measure and paint in the same frame, or
  // the pill is visibly wrong for one frame on every route change.
  useLayoutEffect(() => {
    measurePill()
    const frame = requestAnimationFrame(() => setSlides(true))
    return () => cancelAnimationFrame(frame)
  }, [measurePill, location.pathname])

  useEffect(() => {
    const nav = navRef.current
    if (!nav) return
    // Two triggers, and both are real: the viewport resizing (ResizeObserver
    // on the nav itself, which also fires when a label re-wraps), and the
    // mono face arriving after first paint, which changes every label's
    // width. Without the second the pill sits a few pixels off until the
    // first route change.
    const observer = new ResizeObserver(measurePill)
    observer.observe(nav)
    let cancelled = false
    document.fonts?.ready.then(() => {
      if (!cancelled) measurePill()
    })
    return () => {
      cancelled = true
      observer.disconnect()
    }
  }, [measurePill])

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
        {/* The island. Below 960px it stretches the full width and keeps
            only the brand and the menu button; the routes and the outbound
            link move into the panel below. */}
        <div className="notch notch--bar">
          <NotchShape />
          <NavLink to="/" end className="brand" aria-label="Orthonym — home">
            <BrandMark />
            <span className="brand__word">Orthonym</span>
          </NavLink>

          <span className="notch__rule" aria-hidden="true" />

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

          <nav
            className={justMoved ? 'site-nav site-nav--arrived' : 'site-nav'}
            aria-label="Main"
            ref={navRef}
          >
            {pill && (
              <span
                className={slides ? 'site-nav__pill site-nav__pill--slides' : 'site-nav__pill'}
                aria-hidden="true"
                style={{ '--pill-x': `${pill.x}px`, '--pill-w': `${pill.w}px` }}
              />
            )}
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

          <span className="notch__rule" aria-hidden="true" />

          {/* Two repositories, two pills: the engine that does the naming
              and this web app. Both labels are needed, because one bare
              "GitHub" cannot say which one it opens. The engine link is
              fixed: a fork with VITE_GITHUB_URL=none still runs this engine. */}
          <a
            className="site-head__ext"
            href={ENGINE_URL}
            target="_blank"
            rel="noopener noreferrer"
            aria-label="The Orthonym engine's source on GitHub (opens in a new tab)"
          >
            <GitHubMark />
            Engine
          </a>

          {GITHUB_URL && (
            <>

              {/* The word and the mark, nothing else -- but wearing the
                  chrome adapted from a rainbow-bordered button reference:
                  a gradient border, a sheen that crosses it on hover, and a
                  bloom underneath. All in gold, because a five-hue
                  gradient is exactly the "colour a reader could mistake for
                  a confidence tier" DESIGN.md refuses; legal here because
                  the header is CHROME, the one place the accent lives.

                  The reference's star and its hardcoded "1.2k" count are
                  both gone by instruction. The count could not have shipped
                  anyway: a made-up number on a real repository is a
                  fabricated claim, and fetching api.github.com per page load
                  would send every visitor's IP to a third party and make
                  Privacy.jsx false. */}
              <a
                className="site-head__ext"
                href={GITHUB_URL}
                target="_blank"
                rel="noopener noreferrer"
                aria-label="This web app's source on GitHub (opens in a new tab)"
              >
                <GitHubMark />
                Web app
              </a>
            </>
          )}
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
              href={ENGINE_URL}
              target="_blank"
              rel="noopener noreferrer"
              aria-label="The Orthonym engine's source on GitHub (opens in a new tab)"
            >
              <GitHubMark />
              Engine
            </a>
            {GITHUB_URL && (
              <a
                className="site-nav__mlink"
                href={GITHUB_URL}
                target="_blank"
                rel="noopener noreferrer"
                aria-label="This web app's source on GitHub (opens in a new tab)"
              >
                <GitHubMark />
                Web app
              </a>
            )}
            {/* The issue tab's link, for the widths where the tab itself is
                hidden (IssueBuddy.jsx): below 960px, which is exactly when
                this menu exists. */}
            {NEW_ISSUE_URL && (
              <a
                className="site-nav__mlink"
                href={NEW_ISSUE_URL}
                target="_blank"
                rel="noopener noreferrer"
                aria-label="Report an issue on GitHub (opens in a new tab)"
              >
                Report an issue
              </a>
            )}
          </nav>
        )}
      </div>
    </header>
  )
}

export default Navigation
