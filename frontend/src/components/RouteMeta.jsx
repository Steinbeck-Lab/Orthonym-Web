import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { metaFor } from '../lib/routeMeta'

// Writes the route's title, description and canonical link into <head>
// (lib/routeMeta.js). The canonical is set ONLY here, never in index.html:
// Google reads the rendered page, and a static canonical that the script then
// changed would send it two answers.
function setHead(selector, create, attr, value) {
  let el = document.head.querySelector(selector)
  if (!el) {
    el = document.createElement(create.tag)
    for (const [k, v] of Object.entries(create.attrs)) el.setAttribute(k, v)
    document.head.append(el)
  }
  el.setAttribute(attr, value)
}

export default function RouteMeta() {
  const { pathname } = useLocation()
  useEffect(() => {
    const { title, description, canonical } = metaFor(pathname)
    document.title = title
    setHead('meta[name="description"]', { tag: 'meta', attrs: { name: 'description' } }, 'content', description)
    setHead('link[rel="canonical"]', { tag: 'link', attrs: { rel: 'canonical' } }, 'href', canonical)
  }, [pathname])
  return null
}
