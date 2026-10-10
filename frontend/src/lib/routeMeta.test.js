import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import { ROUTE_META, SITE_URL, metaFor } from './routeMeta.js'

test('every title names the site and every description fits a search snippet', () => {
  for (const [path, { title, description }] of Object.entries(ROUTE_META)) {
    assert.ok(title.includes('Orthonym'), `${path} title lacks the name`)
    assert.ok(description.length <= 160, `${path} description is ${description.length} chars`)
  }
})

test('an unknown path is canonicalised to Home, which is where the router sends it', () => {
  assert.equal(metaFor('/nope').canonical, `${SITE_URL}/`)
  assert.equal(metaFor('/about').canonical, `${SITE_URL}/about`)
  // The router matches /About/ to the About page, so the head must too.
  assert.equal(metaFor('/About/').canonical, `${SITE_URL}/about`)
  assert.equal(metaFor('/explain', 'https://names.example.org').canonical, 'https://names.example.org/explain')
})

test('the sitemap lists exactly the routes that have their own head entries', () => {
  const xml = readFileSync(new URL('../../public/sitemap.xml', import.meta.url), 'utf8')
  const listed = [...xml.matchAll(/<loc>([^<]+)<\/loc>/g)].map((m) => m[1].replace(SITE_URL, ''))
  assert.deepEqual(listed.sort(), Object.keys(ROUTE_META).sort())
})

test("index.html's own title and description are Home's, so the first response agrees with the app", () => {
  const html = readFileSync(new URL('../../index.html', import.meta.url), 'utf8')
  const { title, description } = ROUTE_META['/']
  assert.ok(html.includes(`<title>${title}</title>`))
  assert.ok(html.includes(`content="${description}"`))
  assert.ok(html.includes(`<meta property="og:title" content="${title}" />`))
})
