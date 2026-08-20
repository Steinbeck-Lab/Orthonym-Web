import { NavLink } from 'react-router-dom'

// The site's index-tab strip. Six destinations, one active at a time.
// The active tab is marked three ways at once — never color alone:
// aria-current="page" (assistive tech), a heavier border + weight
// (sighted, non-color), and the sole accent thread on that border
// (the one place outside the Translate button / PIN tile it appears).
const NAV_LINKS = [
  { to: '/', label: 'Translate', end: true },
  { to: '/structure', label: 'Structure → IUPAC' },
  { to: '/from-name', label: 'IUPAC → Structure' },
  { to: '/teach', label: 'Learn' },
  { to: '/explain', label: 'Explain' },
  { to: '/health', label: 'Health Check' },
  { to: '/about', label: 'About' },
]

function Navigation() {
  return (
    <nav className="site-nav page-shell" aria-label="Main">
      <ul className="site-nav__list">
        {NAV_LINKS.map((link) => (
          <li key={link.to} className="site-nav__item">
            <NavLink
              to={link.to}
              end={link.end}
              className={({ isActive }) =>
                isActive ? 'site-nav__link site-nav__link--active' : 'site-nav__link'
              }
            >
              {link.label}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  )
}

export default Navigation
