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
})

test('the sitemap lists exactly the routes that have their own head entries', () => {
  const xml = readFileSync(new URL('../../public/sitemap.xml', import.meta.url), 'utf8')
  const listed = [...xml.matchAll(/<loc>([^<]+)<\/loc>/g)].map((m) => m[1].replace(SITE_URL, ''))
  assert.deepEqual(listed.sort(), Object.keys(ROUTE_META).sort())
})
