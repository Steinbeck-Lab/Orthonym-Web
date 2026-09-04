import { BrowserRouter, Navigate, Outlet, Route, Routes } from 'react-router-dom'
import Navigation from './components/Navigation'
import Footer from './components/Footer'
import Home from './pages/Home'
import IupacToSmiles from './pages/IupacToSmiles'
import Explain from './pages/Explain'
import About from './pages/About'
import './App.css'

// The page's ground. Three very large, very soft crimson-and-grey fields that
// drift across each other, fixed behind everything, so the grey bench the
// cards sit on is a gradient rather than a flat fill. Decorative and
// aria-hidden.
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
