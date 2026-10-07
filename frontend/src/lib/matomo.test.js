import { strict as assert } from 'node:assert'
import { test } from 'node:test'

import { MATOMO, pageUrl, pageViewCommands, resolveMatomo, serverFactsKnown, setupCommands } from './matomo.js'

test('off unless both build args are set: unset args arrive as empty strings', () => {
  assert.equal(resolveMatomo('', ''), null)
  assert.equal(resolveMatomo(undefined, undefined), null)
  assert.equal(resolveMatomo('https://matomo.nfdi4chem.de/', ''), null)
  assert.equal(resolveMatomo('', '10'), null)
  // node --test has no import.meta.env: the tests themselves load no tracker.
  assert.equal(MATOMO, null)
})

test('the snippet\'s protocol-relative URL becomes https, with one trailing slash', () => {
  assert.deepEqual(resolveMatomo('//matomo.nfdi4chem.de/', '10'), { url: 'https://matomo.nfdi4chem.de/', siteId: '10' })
  assert.deepEqual(resolveMatomo('https://matomo.nfdi4chem.de', ' 10 '), { url: 'https://matomo.nfdi4chem.de/', siteId: '10' })
})

test('a URL that is not http(s), or a site id that is not a number, is off', () => {
  assert.equal(resolveMatomo('javascript:alert(1)//', '10'), null)
  assert.equal(resolveMatomo('matomo.nfdi4chem.de', '10'), null)
  assert.equal(resolveMatomo('https://matomo.nfdi4chem.de/', '10;x'), null)
})

test('cookies, device details and load timings are off before the tracker is pointed anywhere', () => {
  const cmds = setupCommands({ url: 'https://m.example/', siteId: '10' })
  assert.deepEqual(cmds.slice(0, 3), [['disableCookies'], ['disableBrowserFeatureDetection'], ['disablePerformanceTracking']])
  assert.deepEqual(cmds.slice(3), [['setTrackerUrl', 'https://m.example/matomo.php'], ['setSiteId', '10']])
})

test('no tracker until the server facts the Privacy page states are recorded', () => {
  assert.equal(serverFactsKnown({ ipBytesMasked: null, rawDataMonths: 6 }), false)
  assert.equal(serverFactsKnown({ ipBytesMasked: 2, rawDataMonths: null }), false)
  assert.equal(serverFactsKnown({ ipBytesMasked: 2, rawDataMonths: 0 }), false)
  assert.equal(serverFactsKnown({ ipBytesMasked: 2, rawDataMonths: 6 }), true)
  assert.equal(serverFactsKnown({ ipBytesMasked: 0, rawDataMonths: 6 }), true)
})

test('no command ever enables link tracking: the report link carries a SMILES', () => {
  const all = [...setupCommands({ url: 'https://m.example/', siteId: '1' }), ...pageViewCommands('https://o.example/', 'T', 'https://o.example/x')]
  assert.equal(all.some(([name]) => /link|download|outlink/i.test(name)), false)
})

test('the reported address drops the query string and the fragment', () => {
  const loc = new URL('https://orthonym.decimer.ai/explain?input=draw&smiles=CCO#part')
  assert.equal(pageUrl(loc), 'https://orthonym.decimer.ai/explain')
})

test('an in-app navigation sends the previous page as referrer; the first view does not', () => {
  assert.deepEqual(pageViewCommands('https://o/a', 'Orthonym', null), [['setCustomUrl', 'https://o/a'], ['setDocumentTitle', 'Orthonym'], ['trackPageView']])
  assert.deepEqual(pageViewCommands('https://o/b', 'Orthonym', 'https://o/a')[0], ['setReferrerUrl', 'https://o/a'])
})
