import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { metaFor } from '../lib/routeMeta'

// Writes the route's title, description and canonical link into <head>
// (lib/routeMeta.js). index.html ships the title and the description tag, so
// only the canonical link is created here. It is set ONLY here, never in
// index.html: Google reads the rendered page, and a static canonical that the
// script then changed would send it two answers.
//
// ponytail: the og: tags in index.html are Home's on every route, because
// link-preview bots run no script; pre-render per route if shared deep links
// need their own previews.
export default function RouteMeta() {
  const { pathname } = useLocation()
  useEffect(() => {
    const { title, description, canonical } = metaFor(pathname, window.location.origin)
    document.title = title
    document.head.querySelector('meta[name="description"]').content = description
    let link = document.head.querySelector('link[rel="canonical"]')
    if (!link) {
      link = Object.assign(document.createElement('link'), { rel: 'canonical' })
      document.head.append(link)
    }
    link.href = canonical
  }, [pathname])
  return null
}
