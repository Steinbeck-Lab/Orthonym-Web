// IUPAC typography: which characters of a name are italic, and which are set
// as a superscript.
//
// WHY THIS IS A FRONTEND PARSER AND NOT A BACKEND FIELD. The name is a plain
// string end to end -- Orthonym emits it, orthonym_service passes it through
// verbatim, and every one of the seven places Orthonym renders a name receives
// that same string. Italics and superscripts are a property of the NAME'S OWN
// SURFACE SYNTAX ("(2S)-", "N,N-", "1H-", "[1,2-a]", "0^4,9"), not of the
// molecule, so they can be read off the string without asking the engine. That
// also makes /from-name work, where the name is the user's own typing and no
// engine ran at all.
//
// WHAT IS AND IS NOT CLAIMED. These runs are TYPOGRAPHY, not chemistry. They
// make no letters-to-atoms claim the way /explain's `name_range` spans do, so
// unlike compute_spans they are deliberately NOT all-or-nothing: a name whose
// stereodescriptor is recognised and whose fusion bracket is not still gets
// the stereodescriptor italicised. Nothing downstream reads them as evidence.
//
// THE STRING IS NEVER MUTATED. Every rule returns OFFSETS into the name the
// backend sent. The one exception is the caret (see `RULES`, rule A), which is
// marked `hidden` rather than deleted -- the caret is superscript notation,
// not part of the printed name, and IUPAC prints the digits raised with no
// caret at all. Copy, CSV and SDF all read the data object, never the DOM
// (verified: CopyButton takes a `text` prop, molExport reads `row.name`), so
// the exact round-trip string is what leaves the page.
//
// Rule sources: IUPAC 2013 recommendations P-14.4 (italicised prefixes,
// stereodescriptors, element-symbol locants, indicated hydrogen, fusion
// letters) and P-23.2.5.1 (von Baeyer superscript locants). The shapes each
// rule matches were taken from what the vendored engine actually emits, not
// from the grammar it could emit.

/**
 * Element symbols that can stand as an italic locant, from Orthonym's own
 * table (assembly/naming_utils.py `_ITALIC_LOCANT_LETTERS`). Two-letter
 * symbols are listed FIRST so alternation prefers "Se" over "S".
 */
const ELEMENT_LOCANTS = ['Si', 'Se', 'Te', 'As', 'Sb', 'Bi', 'Al', 'N', 'O', 'S', 'P', 'C', 'B']

/**
 * Prefixes printed in italic. Every one is matched only at a token boundary
 * (start of the name, or after a hyphen, comma, bracket or space) -- without
 * that guard "n" would match the "n" of "propan-2-ol", which is the letter
 * before a locant hyphen in a great many perfectly ordinary names.
 *
 * `iso` and `neo` are deliberately absent: IUPAC sets those in roman.
 */
const ITALIC_PREFIXES = [
  'tert', 'sec', 'cis', 'trans', 'rel', 'rac', 'syn', 'anti', 'endo', 'exo',
  'abeo', 'ortho', 'meta', 'para', 'n', 'o', 'm', 'p',
]

/** A single CIP-style descriptor unit inside a stereo bracket: "2S", "4as", "R". */
const STEREO_UNIT = "(?:RS|SR|\\d*[a-z]?[RSEZrsez]\\*?|\\u00b1)"

const TOKEN_START = '(^|[\\s\\-,([])'

/**
 * The rules, in priority order. An earlier rule owns a character outright; a
 * later rule may not restyle it. Order matters in exactly one place and it is
 * worth stating: STEREO comes before ELEMENT_LOCANT so that the "S" of
 * "(1S,4R)-" is claimed as a stereodescriptor rather than as a sulfur locant.
 * Both would italicise it, but only the locant rule would go looking for a
 * superscript number after it.
 *
 * Each rule is a regex plus a function turning one match into runs. `index` is
 * the match's offset in the whole name.
 */
const RULES = [
  // A. VON BAEYER / POLYSPIRO SUPERSCRIPT LOCANTS.
  //    Orthonym writes these with a bare caret and says so in the emitter's
  //    own docstring ("PIN superscript typography", rules/polycyclic.py) --
  //    `tricyclo[5.3.2.0^4,9]dodecane`, `trispiro[2.1.2^5.1.3^9.1^3]tridecane`.
  //    The superscript runs to the next "." or "]", and is either a comma-
  //    joined PAIR (von Baeyer secondary bridge) or a SINGLE number (branched
  //    polyspiro revisit locant), so both shapes are matched here.
  {
    name: 'caret',
    re: /\^(\d+(?:,\d+)*)/g,
    runs: (m, index) => [
      { start: index, end: index + 1, style: 'hidden' },
      { start: index + 1, end: index + 1 + m[1].length, style: 'super' },
    ],
  },

  // B. LAMBDA-CONVENTION BONDING NUMBER.
  //    The engine emits a Greek lambda and a PLAIN digit (`hexafluoro-λ6-
  //    sulfane`), while it emits a real Unicode superscript for the eta of a
  //    hapticity (`η⁵`). IUPAC raises both. Raising the lambda digit here is
  //    what makes the two consistent on screen; the string itself keeps its
  //    plain digit, which is what OPSIN must parse back.
  {
    name: 'lambda',
    re: /λ(\d+)/g,
    runs: (m, index) => [
      { start: index + 1, end: index + 1 + m[1].length, style: 'super' },
    ],
  },

  // C. STEREODESCRIPTORS IN PARENTHESES.
  //    "(R)-", "(2E)-", "(1S,4R)-", "(4as,8as)-". Only the CIP LETTERS are
  //    italic: the locants and the punctuation around them stay roman, and in
  //    "4as" the "a" belongs to the locant "4a" while the "s" is the
  //    descriptor. The trailing "-" is required, which is what keeps ordinary
  //    substituent brackets -- "(2-aminoethyl)-", "(propan-2-yl)-" -- out.
  {
    name: 'stereo',
    re: new RegExp(`\\((${STEREO_UNIT}(?:,${STEREO_UNIT})*)\\)(?=-)`, 'g'),
    runs: (m, index) => {
      const body = m[1]
      const bodyStart = index + 1
      const out = []
      for (let i = 0; i < body.length; i += 1) {
        const ch = body[i]
        const isUpper = ch === 'R' || ch === 'S' || ch === 'E' || ch === 'Z'
        // A lowercase descriptor is only a descriptor when it ENDS its unit;
        // otherwise it is the letter half of a composite locant ("4a").
        const next = body[i + 1]
        const isLower =
          (ch === 'r' || ch === 's' || ch === 'e' || ch === 'z') &&
          (next === undefined || next === ',' || next === '*')
        if (isUpper || isLower) out.push({ start: bodyStart + i, end: bodyStart + i + 1, style: 'italic' })
      }
      return out
    },
  },

  // D. ELEMENT-SYMBOL LOCANTS.
  //    "N-methylbenzamide", "N,N-dimethylformamide", "O-methylhydroxylamine",
  //    "Se-methyl ethaneselenoate", and the primed/numbered form the engine
  //    documents at composer.py:5818 -- "N''1-ethyl-N1,N1-dimethyl...". The
  //    element symbol and its primes are italic; the locant NUMBER is a
  //    superscript, which is how IUPAC prints N1 (as N with a raised 1) and
  //    the reason the engine's flat ASCII spelling looks wrong on screen.
  //
  //    An uppercase letter is safe to key on here: an IUPAC name is lowercase
  //    everywhere except these locants, indicated hydrogen, D/L and the
  //    contents of a stereo bracket -- and the three of those that could
  //    collide are all claimed by an earlier or a narrower rule.
  {
    name: 'element-locant',
    re: new RegExp(`${TOKEN_START}(${ELEMENT_LOCANTS.join('|')})('*)(\\d*)(?=[,\\-])`, 'g'),
    runs: (m, index) => {
      const start = index + m[1].length
      const symbolEnd = start + m[2].length + m[3].length
      const out = [{ start, end: symbolEnd, style: 'italic' }]
      if (m[4]) out.push({ start: symbolEnd, end: symbolEnd + m[4].length, style: 'super' })
      return out
    },
  },

  // E. CONFIGURATIONAL PREFIXES D- AND L-.
  //    "D-alanine", "L-tryptophan", "beta-D-glucopyranose". IUPAC sets these
  //    as italic small capitals; with no small-cap face in the system they are
  //    italic here, which is the half of the convention a reader needs to see
  //    that the letter is a descriptor and not an element symbol.
  {
    name: 'configurational',
    re: new RegExp(`${TOKEN_START}(DL|D|L)(?=-)`, 'g'),
    runs: (m, index) => [
      { start: index + m[1].length, end: index + m[1].length + m[2].length, style: 'italic' },
    ],
  },

  // F. ITALIC WORD PREFIXES.
  //    Of these only "tert-" ships from this engine under Orthonym's PIN
  //    configuration; the rest are here for /from-name, where the string is
  //    whatever the visitor typed and "cis-", "n-" and "p-" are all names a
  //    chemist reaches for. The token-boundary guard is load-bearing -- see
  //    ITALIC_PREFIXES.
  {
    name: 'prefix',
    re: new RegExp(`${TOKEN_START}(${ITALIC_PREFIXES.join('|')})(?=-)`, 'g'),
    runs: (m, index) => [
      { start: index + m[1].length, end: index + m[1].length + m[2].length, style: 'italic' },
    ],
  },

  // G. ALPHA / BETA STEREO PREFIXES.
  //    The engine spells these as ASCII words joined straight to the locant --
  //    "3beta-hydroxy-5beta-androstan-17-one", "alpha-D-glucopyranoside"
  //    (rules/steroid_stereo.py `_SIGN`). They stand for the Greek letters,
  //    which IUPAC prints italic. The word is NOT replaced by the Greek
  //    letter: that would change the characters, and OPSIN parses the word.
  {
    name: 'greek-word',
    re: /(^|[\d\s\-,([])(alpha|beta)(?=-)/g,
    runs: (m, index) => [
      { start: index + m[1].length, end: index + m[1].length + m[2].length, style: 'italic' },
    ],
  },

  // H. INDICATED HYDROGEN.
  //    The italic H of "1H-indole", "9H-carbazole", and mid-name after a hydro
  //    prefix as in "3,7-dihydro-1H-purine-2,6-dione". Keyed on a capital H
  //    that follows a locant and closes its token, which is the only shape the
  //    engine emits it in.
  //    The locant is not always a bare digit. It can carry a ring-junction
  //    letter (`9aH-quinolizine`) or a prime, and the primed form is emitted:
  //    spiro.py:2589 builds each token as f"{loc}{prime}H" and its own comment
  //    names the case -- "the 1'H,3'H of a benzodithiophene spiro'd at 2'/6'
  //    DO front-cite". Keyed on a digit only, this marked the `1H` of
  //    `1H,3'H-spiro[...]` and left the `3'H` beside it roman, splitting one
  //    prefix down the middle. Only the H is ever italic; the locant and its
  //    prime stay roman.
  {
    name: 'indicated-hydrogen',
    re: /(\d[a-z]?'*)(H)(?=[-\]),]|$)/g,
    runs: (m, index) => [
      { start: index + m[1].length, end: index + m[1].length + 1, style: 'italic' },
    ],
  },
]

/**
 * Fusion-descriptor letters: the "b" of `naphtho[2,3-b]furan`, the "a" of
 * `benzo[a]pyrene`, the three of `benzo[ghi]perylene`, both letters of a
 * bis-fusion `[1,2-a:3,4-a']`, and both of `dibenzo[b,d]furan`.
 *
 * A fusion letter is NOT always preceded by a hyphen. It is when the bracket
 * also carries the attachment locants (`[2,3-b]`), and it is not when the
 * bracket is peripheral-letters-only (`[a]`, `[b,d]`, `[ghi]`, `[cd,f]`) --
 * which is the commoner shape, and the one the first version of this function
 * missed entirely. So a letter run may open the bracket or follow any of
 * `-`, `,`, `:` or `;` (all four are already admitted by the body test, and
 * leaving `;` out of the separators made `[b;c]` mark nothing).
 *
 * Handled apart from RULES because it needs a WHOLE-BRACKET decision rather
 * than a local match: a bracket qualifies only if EVERY letter in it sits in
 * a fusion position. That is what keeps `[1,1'-biphenyl]` out -- it opens with
 * a "-bip" that looks exactly like a fusion run until you notice the "henyl"
 * after it -- and `spiro[cyclohexane-1,2'-oxirane]` with it, while letting the
 * von Baeyer brackets through untouched because they hold no letters at all.
 */
function fusionRuns(name) {
  const out = []
  const brackets = /\[([^[\]]*)\]/g
  let bracket
  while ((bracket = brackets.exec(name)) !== null) {
    const body = bracket[1]
    const bodyStart = bracket.index + 1
    if (!/^[0-9a-z,':;.-]+$/.test(body)) continue
    // A run is letters with primes among or after them -- `b`, `a'`, `ghi`,
    // `efghi`, and the `d'e'f'` of `anthra[2,1,9-def:6,5,10-d'e'f']-
    // diisoquinoline`, the perylene-diimide core the engine ships verbatim
    // from its retained fused-heterocycle table. The prime belongs to the
    // letter and is italic with it.
    //
    // THE FIVE-LETTER CAP IS LOAD-BEARING, not a guess at the longest real
    // set. `efghi` is five, and eight would swallow the `biphenyl` of
    // `[1,1'-biphenyl]` whole -- at which point every letter in that bracket
    // WOULD be covered, the guard below would pass, and a substituent name
    // would be italicised as a fusion descriptor. Raise it only with a
    // replacement for that guard.
    const letters = /(?:^|[-,:;])([a-z](?:'*[a-z]){0,4}'*)/g
    const found = []
    let covered = 0
    let hit
    while ((hit = letters.exec(body)) !== null) {
      // hit.index is the separator (or 0 when the run opens the bracket), so
      // the run starts at the end of the match less the run itself.
      const start = bodyStart + hit.index + hit[0].length - hit[1].length
      found.push({ start, end: start + hit[1].length })
      covered += (hit[1].match(/[a-z]/g) || []).length
    }
    // Every letter in the bracket has to be accounted for by a fusion
    // position. One stray letter and this is not a fusion descriptor.
    const totalLetters = (body.match(/[a-z]/g) || []).length
    if (found.length === 0 || covered !== totalLetters) continue
    for (const run of found) out.push({ ...run, style: 'italic' })
  }
  return out
}

/**
 * Collapses raw runs into a sorted, non-overlapping list. First writer wins a
 * character, which is what gives RULES its priority order.
 */
function settle(raw, length) {
  const owner = new Array(length).fill(null)
  for (const run of raw) {
    for (let i = Math.max(0, run.start); i < Math.min(length, run.end); i += 1) {
      if (owner[i] === null) owner[i] = run.style
    }
  }
  const out = []
  let start = 0
  for (let i = 1; i <= length; i += 1) {
    if (i === length || owner[i] !== owner[start]) {
      if (owner[start] !== null) out.push({ start, end: i, style: owner[start] })
      start = i
    }
  }
  return out
}

/**
 * The styled ranges of an IUPAC name, sorted and non-overlapping. Characters
 * not covered by a run are plain. `style` is one of:
 *
 *   'italic'  set in the italic face
 *   'super'   raised
 *   'hidden'  not printed at all (the superscript caret, and only that)
 */
export function nameRuns(name) {
  if (!name) return []
  const raw = []
  for (const rule of RULES) {
    rule.re.lastIndex = 0
    let match
    while ((match = rule.re.exec(name)) !== null) {
      raw.push(...rule.runs(match, match.index))
      // A zero-length match would spin here; every rule above consumes at
      // least one character, but the guard costs nothing and a future rule
      // with an all-optional tail would otherwise hang the page.
      if (match[0].length === 0) rule.re.lastIndex += 1
    }
  }
  raw.push(...fusionRuns(name))
  return settle(raw, name.length)
}

/**
 * The styled ranges of a molecular FORMULA -- `C8H10N4O2` reads C8H10N4O2 with
 * every count subscript, and a trailing charge raised.
 *
 * Formulas are a separate alphabet from names and share none of the rules
 * above: a digit after an element symbol is a count, never a locant.
 */
export function formulaRuns(formula) {
  if (!formula) return []
  const raw = []
  const atoms = /([A-Z][a-z]?)(\d+)/g
  let atom
  while ((atom = atoms.exec(formula)) !== null) {
    const digitsStart = atom.index + atom[1].length
    raw.push({ start: digitsStart, end: digitsStart + atom[2].length, style: 'sub' })
  }
  // A charge closes the formula: "C5H6N+", "C5H6N+2", "SO4-2". RDKit writes
  // the sign before the magnitude; both orders are accepted here because the
  // formula also reaches this function from /from-name, unnormalised.
  const charge = /(?:[+-]\d*|\d*[+-])$/.exec(formula)
  if (charge && charge[0]) {
    raw.push({ start: charge.index, end: formula.length, style: 'super' })
  }
  return settle(raw, formula.length)
}

/**
 * Cuts `text[from:to)` into a gapless list of `{ text, style }` pieces, with
 * `style` null for the plain stretches.
 *
 * The range arguments are what lets /explain compose this with its own
 * character spans: that page has already cut the name into hover targets by
 * `name_range` offset, and each of those pieces asks here for the typography
 * inside its own range rather than re-parsing a fragment -- a fragment can cut
 * a token in half, and half a token parses as nothing.
 */
export function applyRuns(text, runs, from = 0, to = text.length) {
  const pieces = []
  let cursor = from
  for (const run of runs) {
    if (run.end <= from || run.start >= to) continue
    const start = Math.max(run.start, from)
    const end = Math.min(run.end, to)
    if (start > cursor) pieces.push({ text: text.slice(cursor, start), style: null })
    pieces.push({ text: text.slice(start, end), style: run.style })
    cursor = end
  }
  if (cursor < to) pieces.push({ text: text.slice(cursor, to), style: null })
  return pieces
}
