// The failure message is a whole sentence ("OPSIN reads this name in a reordered
// form (for example a CAS index name), so its parts cannot be matched to the text.
// Try the IUPAC form."). It must not inherit the uppercase mono caption style of the
// one-word pending label (final review M9). Static checks of the two files that
// decide it: the page gives the error caption the sentence modifier, and the
// stylesheet's modifier undoes the caption's case and tracking.
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const jsx = readFileSync(new URL('./Explain.jsx', import.meta.url), 'utf8')
const css = readFileSync(new URL('./Explain.css', import.meta.url), 'utf8')

test('the error caption carries the sentence modifier and the pending label does not', () => {
  const error = jsx.match(/role="alert">[\s\S]*?<span className="([^"]+)">\s*\{apiError/)
  assert.ok(error, 'the error branch renders apiError in a span')
  assert.match(error[1], /explain-patch__state-label--sentence/)
  const pending = jsx.match(/<span className="([^"]+)">Naming and decomposing/)
  assert.ok(pending)
  assert.doesNotMatch(pending[1], /--sentence/)
})

test('the sentence modifier is sentence case in body type, after the caption rule', () => {
  const rule = css.match(/\.explain-patch__state-label--sentence\s*\{([^}]*)\}/)
  assert.ok(rule, 'the modifier has a rule')
  assert.match(rule[1], /text-transform:\s*none/)
  assert.match(rule[1], /letter-spacing:\s*normal/)
  assert.match(rule[1], /font-family:\s*var\(--font-body\)/)
  assert.ok(css.indexOf('.explain-patch__state-label--sentence') > css.indexOf('.explain-patch__state-label {'),
    'declared after the caption rule so it wins at equal specificity')
})
