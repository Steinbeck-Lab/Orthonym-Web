import { BrowserRouter, Routes, Route, Outlet } from 'react-router-dom'
import Navigation from './components/Navigation'
import Footer from './components/Footer'
import Home from './pages/Home'
import StructureToIupac from './pages/StructureToIupac'
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
          <Route path="/structure" element={<StructureToIupac />} />
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
