import { BrowserRouter, Navigate, Outlet, Route, Routes } from 'react-router-dom'
import Navigation from './components/Navigation'
import Footer from './components/Footer'
import Home from './pages/Home'
import IupacToSmiles from './pages/IupacToSmiles'
import Explain from './pages/Explain'
import About from './pages/About'
import './App.css'

// The page's ground: FOUR corner fields, a centre glow and a fine dot grid,
// fixed behind everything, so the bench the cards sit on is a composition
// rather than a flat fill. Decorative and aria-hidden throughout.
//
// Rebuilt 2026-09-05 on an owner-supplied reference ("aurora dream corner
// whispers" + a soft centre glow + a noise-dot texture), at the BOLD strength
// the owner picked and in STITCH's own ramp -- crimson, its wash and its deep
// shade, plus the cool greys. The reference's lilac, cream, pink and blue do
// not survive the translation; four DIFFERENT hues would put colour on the
// ground that a reader could mistake for a confidence tier, which the whole
// system forbids. Four different WEIGHTS of the one accent do the same
// compositional job and cannot be misread.
//
// The yellow in the second reference is refused outright and deliberately:
// `--glow` is functional here. It means "you are pointing at these atoms
// right now", and spending it on the page background would spend the one
// signal /explain's whole interaction rests on.
//
// Why it is here in the shell and not in index.css: the drift is done with
// transforms on separate layers, which the compositor can move without
// repainting. Animating background-position on one full-viewport element
// would repaint the whole page on every frame, all the time, on every route.
function GradientGround() {
  return (
    <div className="ground" aria-hidden="true">
      <span className="ground__field ground__field--a" />
      <span className="ground__field ground__field--b" />
      <span className="ground__field ground__field--c" />
      <span className="ground__field ground__field--d" />
      <span className="ground__glow" />
      <span className="ground__grain" />
    </div>
  )
}

// Shared shell for every route: the nav strip on top, the matched page's
// own content in the middle, and the footer pinned beneath it.
function Layout() {
  return (
    <div className="page">
      <GradientGround />
      <Navigation />
      {/* The route's content lives in its own box so the FOOTER can be
          pinned to the bottom of the viewport: the page is exactly one
          screen tall and this is the part that gives, rather than the whole
          document growing and pushing the footer below the fold.
          Home is compressed to fit it outright; the long reading pages
          (About, Explain) scroll inside here, with the header and footer
          staying put. */}
      <div className="page__content">
        <Outlet />
      </div>
      <Footer />
    </div>
  )
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Home />} />
          {/* /structure and /teach are folded into /explain (spec section 12).
              Redirects, not deletions: both were linked from the nav for
              months and a 404 loses a bookmark for nothing. `replace` so the
              back button does not bounce off the redirect.

              Both land on /explain?input=draw, so an old link keeps its old
              BEHAVIOUR and not just its old URL -- someone who bookmarked
              /teach did it to draw a molecule. */}
          <Route path="/structure" element={<Navigate to="/explain?input=draw" replace />} />
          <Route path="/teach" element={<Navigate to="/explain?input=draw" replace />} />
          <Route path="/from-name" element={<IupacToSmiles />} />
          <Route path="/explain" element={<Explain />} />
          {/* Health Check folded into About as a compact status board
              (Task 18, owner instruction: "move the health check to about
              and keep it as a message board rather than a whole page").
              Redirect, not a deletion, for the same reason /structure and
              /teach redirect above: months of bookmarks and links to
              /health should not 404. `replace` so the back button does not
              bounce off the redirect. */}
          <Route path="/health" element={<Navigate to="/about" replace />} />
          <Route path="/about" element={<About />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App
