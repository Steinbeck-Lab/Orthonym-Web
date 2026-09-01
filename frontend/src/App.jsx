import { BrowserRouter, Navigate, Outlet, Route, Routes } from 'react-router-dom'
import Navigation from './components/Navigation'
import Footer from './components/Footer'
import Home from './pages/Home'
import IupacToSmiles from './pages/IupacToSmiles'
import Explain from './pages/Explain'
import HealthCheck from './pages/HealthCheck'
import About from './pages/About'
import './App.css'

// Shared shell for every route: the nav strip on top, the matched page's
// own content in the middle, and the footer pinned beneath it.
function Layout() {
  return (
    <div className="page">
      <Navigation />
      <Outlet />
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
          <Route path="/health" element={<HealthCheck />} />
          <Route path="/about" element={<About />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App
