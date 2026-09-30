import test from 'node:test'
import assert from 'node:assert/strict'

import { nameRuns, formulaRuns, applyRuns, breakSegments } from './nameTypography.js'

// Every name in this file is a REAL string the vendored engine produced, or a
// real string a chemist would type into /from-name. None of them are invented
// to fit the parser.

/** The name with each styled run wrapped, for a readable assertion. */
function marked(name) {
  const wrap = { italic: ['{', '}'], super: ['^{', '}'], sub: ['_{', '}'], hidden: ['', ''] }
  return applyRuns(name, nameRuns(name))
    .map(({ text, style }) => {
      if (style === 'hidden') return ''
      if (!style) return text
      const [open, close] = wrap[style]
      return `${open}${text}${close}`
    })
    .join('')
}

// ------------------------------------------------------ superscripts

test('a von Baeyer caret raises its locant pair and prints no caret', () => {
  assert.equal(marked('tricyclo[5.3.2.0^4,9]dodecane'), 'tricyclo[5.3.2.0^{4,9}]dodecane')
})

test('every caret in a cage is raised, not just the first', () => {
  assert.equal(
    marked('pentacyclo[4.3.0.0^2,5.0^3,8.0^4,7]nonane'),
    'pentacyclo[4.3.0.0^{2,5}.0^{3,8}.0^{4,7}]nonane'
  )
})

test('a branched-polyspiro caret raises a single locant', () => {
  assert.equal(marked('trispiro[2.1.2^5.1.3^9.1^3]tridecane'), 'trispiro[2.1.2^{5}.1.3^{9}.1^{3}]tridecane')
})

test('the lambda bonding number is raised', () => {
  assert.equal(marked('hexafluoro-λ6-sulfane'), 'hexafluoro-λ^{6}-sulfane')
})

test('an eta hapticity is left alone: the engine already wrote it raised', () => {
  assert.equal(marked('bis(η⁵-cyclopentadienyl)iron'), 'bis(η⁵-cyclopentadienyl)iron')
})

// ------------------------------------------------------ stereodescriptors

test('a bare CIP descriptor is italic and its brackets are not', () => {
  assert.equal(marked('(S)-bromo(chloro)(fluoro)methane'), '({S})-bromo(chloro)(fluoro)methane')
})

test('a locant stays roman beside its descriptor', () => {
  assert.equal(marked('(2E)-but-2-ene'), '(2{E})-but-2-ene')
  assert.equal(marked('(2S)-butan-2-ol'), '(2{S})-butan-2-ol')
})

test('every descriptor in a multi-centre bracket is italic', () => {
  assert.equal(
    marked('(1S,4R)-1,7,7-trimethylbicyclo[2.2.1]heptan-2-one'),
    '(1{S},4{R})-1,7,7-trimethylbicyclo[2.2.1]heptan-2-one'
  )
})

test('in a composite locant only the descriptor letter is italic, not the locant letter', () => {
  // "4a" is the locant; the trailing "s" is the pseudo-asymmetry descriptor.
  assert.equal(marked('(4as,8as)-decahydronaphthalene'), '(4a{s},8a{s})-decahydronaphthalene')
})

test('an ordinary substituent bracket is not a stereo bracket', () => {
  assert.equal(marked('(propan-2-yl)benzene'), '(propan-2-yl)benzene')
  assert.equal(marked('(butan-2-yl)benzene'), '(butan-2-yl)benzene')
})

// ------------------------------------------------------ element-symbol locants

test('an element-symbol locant is italic', () => {
  assert.equal(marked('N-methylbenzamide'), '{N}-methylbenzamide')
  assert.equal(marked('O-methylhydroxylamine'), '{O}-methylhydroxylamine')
  assert.equal(marked('S-ethyl ethanethioate'), '{S}-ethyl ethanethioate')
})

test('a two-letter element-symbol locant is italic whole', () => {
  assert.equal(marked('Se-methyl ethaneselenoate'), '{Se}-methyl ethaneselenoate')
})

test('a repeated locant is italic at every occurrence', () => {
  assert.equal(marked('N,N-dimethylformamide'), '{N},{N}-dimethylformamide')
})

test('a numbered element locant raises its number and italicises its primes', () => {
  assert.equal(
    marked("N''1-ethyl-N1,N1-dimethylcyclohexane-1,1-dicarboximidamide"),
    "{N''}^{1}-ethyl-{N}^{1},{N}^{1}-dimethylcyclohexane-1,1-dicarboximidamide"
  )
})

test('a mid-name element locant is found, not just a leading one', () => {
  assert.equal(
    marked('N1-(2-aminoethyl)-N1,N2,N2-trimethylethane-1,2-diamine'),
    '{N}^{1}-(2-aminoethyl)-{N}^{1},{N}^{2},{N}^{2}-trimethylethane-1,2-diamine'
  )
})

test('a second word carries its own locant', () => {
  assert.equal(marked('N,N-dimethylmethanamine N-oxide'), '{N},{N}-dimethylmethanamine {N}-oxide')
})

// ------------------------------------------------------ indicated hydrogen

test('indicated hydrogen is italic and its locant is not', () => {
  assert.equal(marked('1H-indole'), '1{H}-indole')
  assert.equal(marked('9H-carbazole'), '9{H}-carbazole')
})

test('indicated hydrogen mid-name is italic', () => {
  assert.equal(
    marked('1,3,7-trimethyl-3,7-dihydro-1H-purine-2,6-dione'),
    '1,3,7-trimethyl-3,7-dihydro-1{H}-purine-2,6-dione'
  )
})

test('indicated hydrogen keeps its H italic at a primed or letter locant', () => {
  // spiro.py builds each token as f"{loc}{prime}H" and front-cites them, so
  // "1H,3'H-" is one prefix. Keyed on a bare digit, this italicised the first
  // H and left the second roman, splitting the prefix down the middle.
  assert.equal(
    marked("1H,3'H-spiro[indene-2,1'-isobenzofuran]"),
    "1{H},3'{H}-spiro[indene-2,1'-isobenzofuran]"
  )
  assert.equal(marked('9aH-quinolizine'), '9a{H}-quinolizine')
  assert.equal(
    marked("4,4a-dihydro-2H,4H-benzo[1,2-b:4,3-c']dipyran-5,6(4aH,6aH)-dione"),
    "4,4a-dihydro-2{H},4{H}-benzo[1,2-{b}:4,3-{c'}]dipyran-5,6(4a{H},6a{H})-dione"
  )
})

test('indicated hydrogen inside a bracket is italic', () => {
  assert.equal(marked('2-amino-3-(1H-indol-3-yl)propanoic acid'), '2-amino-3-(1{H}-indol-3-yl)propanoic acid')
})

// ------------------------------------------------------ fusion letters

test('a fusion letter is italic and its locants are not', () => {
  assert.equal(marked('imidazo[1,2-a]pyridine'), 'imidazo[1,2-{a}]pyridine')
  assert.equal(marked('naphtho[2,3-b]furan'), 'naphtho[2,3-{b}]furan')
})

test('a fusion letter and an indicated hydrogen coexist', () => {
  assert.equal(marked('1H-imidazo[4,5-d]pyrimidine'), '1{H}-imidazo[4,5-{d}]pyrimidine')
})

test('a fusion letter with no locants before it is italic', () => {
  // The COMMONER shape, and the one the first version of fusionRuns missed:
  // a peripheral-letters-only bracket carries no hyphen at all.
  assert.equal(marked('benzo[a]pyrene'), 'benzo[{a}]pyrene')
  assert.equal(marked('benzo[b]thiophene'), 'benzo[{b}]thiophene')
  assert.equal(marked('cyclopenta[a]phenanthrene'), 'cyclopenta[{a}]phenanthrene')
})

test('every letter of a multi-letter fusion bracket is italic', () => {
  assert.equal(marked('dibenzo[b,d]furan'), 'dibenzo[{b},{d}]furan')
  assert.equal(marked('benzo[ghi]perylene'), 'benzo[{ghi}]perylene')
  assert.equal(marked('anthra[2,1,9-def]isoquinoline'), 'anthra[2,1,9-{def}]isoquinoline')
})

test('both bracket shapes are italic in the same name', () => {
  // The failure that made this worth fixing: one name, two spellings, and only
  // the hyphenated one marked -- so the "a" and "h" read as ordinary letters
  // while the "f" beside them read as a descriptor.
  assert.equal(
    marked('benzo[a]benzo[5,6]indeno[2,1-f]cyclopenta[h]azulene'),
    'benzo[{a}]benzo[5,6]indeno[2,1-{f}]cyclopenta[{h}]azulene'
  )
})

test('a primed fusion set is italic, primes and all', () => {
  // The perylene-diimide core, shipped verbatim from the engine's retained
  // fused-heterocycle table (data/fused_heterocycles.py). A prime BETWEEN two
  // letters used to break the whole-bracket coverage count, which threw away
  // the good "def" run along with the "d'e'f'" one and left the name roman.
  assert.equal(
    marked("anthra[2,1,9-def:6,5,10-d'e'f']diisoquinoline"),
    "anthra[2,1,9-{def}:6,5,10-{d'e'f'}]diisoquinoline"
  )
  assert.equal(marked("benzo[1,2-b:4,3-c']dipyran"), "benzo[1,2-{b}:4,3-{c'}]dipyran")
})

test('a five-letter fusion set is italic', () => {
  assert.equal(marked('phenanthro[5,4,3,2-efghi]perylene'), 'phenanthro[5,4,3,2-{efghi}]perylene')
})

test('a spiro bracket naming two rings is not a fusion bracket', () => {
  for (const name of [
    "spiro[cyclohexane-1,2'-oxirane]",
    "spiro[bicyclo[2.2.1]heptane-7,2'-bicyclo[3.2.1]octane]",
  ]) {
    assert.equal(marked(name), name, name)
  }
})

test('a biphenyl bracket is not a fusion bracket', () => {
  // "[1,1'-biphenyl]" has a "-b" in exactly the shape of a fusion letter. It
  // is not one, and the whole-bracket check is what tells them apart.
  assert.equal(marked("[1,1'-biphenyl]-2,2'-diol"), "[1,1'-biphenyl]-2,2'-diol")
})

test('a von Baeyer bracket holds no fusion letter', () => {
  assert.equal(marked('bicyclo[2.2.2]octane'), 'bicyclo[2.2.2]octane')
  assert.equal(marked('7-oxabicyclo[2.2.1]heptane'), '7-oxabicyclo[2.2.1]heptane')
})

// ------------------------------------------------------ word prefixes

test('tert- is italic', () => {
  assert.equal(marked('tert-butylbenzene'), '{tert}-butylbenzene')
})

test('a mid-name tert- is italic', () => {
  assert.equal(marked('1-tert-butyl-4-methylbenzene'), '1-{tert}-butyl-4-methylbenzene')
})

test('typed cis-, trans- and n- are italic on /from-name', () => {
  assert.equal(marked('cis-but-2-ene'), '{cis}-but-2-ene')
  assert.equal(marked('trans-but-2-ene'), '{trans}-but-2-ene')
  assert.equal(marked('n-butyl acetate'), '{n}-butyl acetate')
})

test('the n before a locant hyphen is NOT a prefix', () => {
  // This is the whole reason the prefixes need a token-boundary guard:
  // "propan-2-ol" ends a token with "n" immediately before a hyphen.
  assert.equal(marked('propan-2-ol'), 'propan-2-ol')
  assert.equal(marked('2-methylpropan-1-ol'), '2-methylpropan-1-ol')
})

test('iso and neo stay roman', () => {
  assert.equal(marked('isopropylbenzene'), 'isopropylbenzene')
  assert.equal(marked('neopentane'), 'neopentane')
})

// ------------------------------------------------------ configurational prefixes

test('D and L are italic', () => {
  assert.equal(marked('D-alanine'), '{D}-alanine')
  assert.equal(marked('L-tryptophan'), '{L}-tryptophan')
})

test('alpha and beta are italic and keep their spelling', () => {
  assert.equal(marked('beta-D-glucopyranose'), '{beta}-{D}-glucopyranose')
  assert.equal(
    marked('3beta-hydroxy-5beta-androstan-17-one'),
    '3{beta}-hydroxy-5{beta}-androstan-17-one'
  )
})

test('a two-sugar name keeps both prefixes', () => {
  assert.equal(
    marked('beta-D-fructofuranosyl alpha-D-glucopyranoside'),
    '{beta}-{D}-fructofuranosyl {alpha}-{D}-glucopyranoside'
  )
})

// ------------------------------------------------------ names that need nothing

test('a plain name is left entirely alone', () => {
  for (const plain of [
    'cyclohexane',
    'propylbenzene',
    '2,2-dimethylpropane',
    'phenylphosphonic acid',
    'spiro[5.5]undecane',
    '1,4,7,10,13,16-hexaoxacyclooctadecane',
  ]) {
    assert.equal(marked(plain), plain, plain)
    assert.deepEqual(nameRuns(plain), [], plain)
  }
})

test('an empty or missing name yields no runs', () => {
  assert.deepEqual(nameRuns(''), [])
  assert.deepEqual(nameRuns(null), [])
  assert.deepEqual(nameRuns(undefined), [])
})

// ------------------------------------------------------ the runs themselves

test('runs are sorted, non-empty and never overlap', () => {
  const names = [
    "N''1-ethyl-N1,N1-dimethylcyclohexane-1,1-dicarboximidamide",
    '(1S,4R)-1,7,7-trimethylbicyclo[2.2.1]heptan-2-one',
    'pentacyclo[4.3.0.0^2,5.0^3,8.0^4,7]nonane',
    '1,3,7-trimethyl-3,7-dihydro-1H-purine-2,6-dione',
    'beta-D-fructofuranosyl alpha-D-glucopyranoside',
  ]
  for (const name of names) {
    const runs = nameRuns(name)
    let previousEnd = 0
    for (const run of runs) {
      assert.ok(run.start >= previousEnd, `${name}: run starts before the last one ended`)
      assert.ok(run.end > run.start, `${name}: empty run`)
      assert.ok(run.end <= name.length, `${name}: run past the end`)
      previousEnd = run.end
    }
  }
})

test('applyRuns rebuilds the exact name when nothing is hidden', () => {
  const name = '(1S,4R)-1,7,7-trimethylbicyclo[2.2.1]heptan-2-one'
  assert.equal(applyRuns(name, nameRuns(name)).map((p) => p.text).join(''), name)
})

test('applyRuns over a sub-range returns only that range', () => {
  const name = 'N-methylbenzamide'
  const runs = nameRuns(name)
  // "N-methyl" -- the italic N is inside, the rest of the name is not.
  const pieces = applyRuns(name, runs, 0, 8)
  assert.equal(pieces.map((p) => p.text).join(''), 'N-methyl')
  assert.deepEqual(pieces[0], { text: 'N', style: 'italic' })
})

test('applyRuns clips a run that straddles the range edge', () => {
  const name = 'tert-butylbenzene'
  const runs = nameRuns(name)
  // Cut through the middle of the italic "tert".
  const pieces = applyRuns(name, runs, 0, 2)
  assert.deepEqual(pieces, [{ text: 'te', style: 'italic' }])
})

// ------------------------------------------------------ formulas

test('a formula subscripts every count', () => {
  const formula = 'C8H10N4O2'
  const out = applyRuns(formula, formulaRuns(formula))
    .map(({ text, style }) => (style === 'sub' ? `_{${text}}` : text))
    .join('')
  assert.equal(out, 'C_{8}H_{10}N_{4}O_{2}')
})

test('a count of one is not written, so nothing is subscripted', () => {
  assert.deepEqual(formulaRuns('CHNO'), [])
})

test('a two-letter element keeps its lowercase letter out of the subscript', () => {
  assert.deepEqual(formulaRuns('SiO2'), [{ start: 3, end: 4, style: 'sub' }])
})

test('a charge is raised, not lowered', () => {
  const runs = formulaRuns('C5H6N+')
  assert.deepEqual(runs[runs.length - 1], { start: 5, end: 6, style: 'super' })
})

test('a magnitude charge is raised whole', () => {
  const runs = formulaRuns('SO4-2')
  assert.deepEqual(runs[runs.length - 1], { start: 3, end: 5, style: 'super' })
})

test('an empty formula yields no runs', () => {
  assert.deepEqual(formulaRuns(''), [])
  assert.deepEqual(formulaRuns(null), [])
})

test('breakSegments cuts only after closing brackets and commas', async () => {
  const { breakSegments } = await import('./nameTypography.js')
  assert.deepEqual(breakSegments('2-[4-(2-methylpropyl)phenyl]propanoic acid'), [
    '2-[4-(2-methylpropyl)',
    'phenyl]',
    'propanoic acid',
  ])
  assert.deepEqual(breakSegments('1,3,7-trimethyl'), ['1,', '3,', '7-trimethyl'])
  // A line never starts with a hyphen, a comma or another closer.
  assert.deepEqual(breakSegments('henicosa-1(20),2,4,8-tetraene'), ['henicosa-1(20),', '2,', '4,', '8-tetraene'])
  assert.deepEqual(breakSegments('(7R,10S)-4,16-dihydroxy'), ['(7R,', '10S)-4,', '16-dihydroxy'])
  // Nothing to cut: one segment, the text unchanged.
  assert.deepEqual(breakSegments('ethanol'), ['ethanol'])
  // Round trip: the segments always rebuild the exact string.
  const name = '(7R,10S)-4,16-dihydroxy-13-methyl-6-oxa-13-azahexacyclo[12.6.1.0^5,20]henicosa-1(20),2-diene'
  assert.equal(breakSegments(name).join(''), name)
})

// ------------------------------------------------------ rule tables and edges

test('every element symbol the engine uses as a locant is italic', () => {
  // The rule is a table; a symbol missing from it is only visible on the one
  // compound that needs it.
  for (const sym of ['Si', 'Se', 'Te', 'As', 'Sb', 'Bi', 'Al', 'N', 'O', 'S', 'P', 'C', 'B']) {
    assert.equal(marked(`${sym}-methylbenzene`), `{${sym}}-methylbenzene`, sym)
  }
  // ...and after an opening bracket, where a substituent's own locant sits.
  assert.equal(marked('2-(N-methylamino)ethanol'), '2-({N}-methylamino)ethanol')
})

test('every italic word prefix is italic before a hyphen', () => {
  for (const p of ['tert', 'sec', 'cis', 'trans', 'rel', 'rac', 'syn', 'anti', 'endo', 'exo', 'abeo', 'ortho', 'meta', 'para', 'n', 'o', 'm', 'p']) {
    assert.equal(marked(`${p}-butane`), `{${p}}-butane`, p)
  }
})

test('a multi-digit lambda number is raised whole', () => {
  assert.equal(marked('1λ10-thiane'), '1λ^{10}-thiane')
})

test('the rarer stereodescriptor shapes are italic where they are descriptors', () => {
  assert.equal(marked('(RS)-butan-2-ol'), '({RS})-butan-2-ol')
  assert.equal(marked('(Z)-but-2-ene'), '({Z})-but-2-ene')
  assert.equal(marked('(2Z)-but-2-ene'), '(2{Z})-but-2-ene')
  assert.equal(marked('(2r)-butan-2-ol'), '(2{r})-butan-2-ol')
  assert.equal(marked('(2e)-but-2-ene'), '(2{e})-but-2-ene')
  assert.equal(marked('(2r*)-butan-2-ol'), '(2{r}*)-butan-2-ol')
  assert.equal(marked('(1R*,2S*)-cyclohexane-1,2-diol'), '(1{R}*,2{S}*)-cyclohexane-1,2-diol')
})

test('DL is italic whole', () => {
  assert.equal(marked('DL-alanine'), '{DL}-alanine')
})

test('a word that merely starts with beta is not a stereo prefix', () => {
  // "betaine" has no hyphen after "beta": italicising it would set part of an
  // ordinary word as a descriptor.
  assert.equal(marked('betaine'), 'betaine')
})

test('a letter-only fusion bracket is italic after either separator', () => {
  assert.equal(marked('benzo[b;c]furan'), 'benzo[{b};{c}]furan')
  assert.equal(marked('benzo[b:c]furan'), 'benzo[{b}:{c}]furan')
})

test('indicated hydrogen at the very end of a name is italic', () => {
  assert.equal(marked('quinolizin-4(1H)-one'), 'quinolizin-4(1{H})-one')
  assert.equal(marked('naphthalene-1H'), 'naphthalene-1{H}')
})

test('applyRuns cuts a range from the middle of a name, keeping runs on both sides out', () => {
  // Explain asks for the typography inside one hover piece at a time. A run
  // that lies wholly before or after the piece must not leak into it, and one
  // straddling its left edge is clipped there.
  const name = 'N-methyl-3,4-dihydro-1H-purine'
  const runs = nameRuns(name)
  const from = name.indexOf('dihydro')
  const to = name.indexOf('purine')
  const pieces = applyRuns(name, runs, from, to)
  assert.deepEqual(pieces.map((p) => p.text).join(''), name.slice(from, to))
  assert.deepEqual(pieces, [
    { text: 'dihydro-1', style: null },
    { text: 'H', style: 'italic' },
    { text: '-', style: null },
  ])
  // A range that starts inside the italic "tert" clips the run at its left edge.
  const t = 'tert-butylbenzene'
  assert.deepEqual(applyRuns(t, nameRuns(t), 2, 6), [
    { text: 'rt', style: 'italic' },
    { text: '-b', style: null },
  ])
})

test('applyRuns makes no empty piece where a range only touches a run', () => {
  // A range that begins where an italic run ends must start on plain text; an
  // empty italic piece in front of it would render as a stray empty element.
  const name = 'N-methyl'
  assert.deepEqual(applyRuns(name, nameRuns(name), 1, 8), [{ text: '-methyl', style: null }])
  const n2 = 'methyl-N'
  assert.deepEqual(applyRuns(n2, nameRuns(n2), 0, 7), [{ text: 'methyl-', style: null }])
})

test('a two-letter element in a formula is not cut in half', () => {
  assert.deepEqual(formulaRuns('C6H4Cl2'), [
    { start: 1, end: 2, style: 'sub' },
    { start: 3, end: 4, style: 'sub' },
    { start: 6, end: 7, style: 'sub' },
  ])
})

test('a break is never offered before another closer, and is offered after a brace', () => {
  // "))" and ")]" are one closing mark; a line that starts with the second
  // half reads as a stray bracket.
  assert.deepEqual(breakSegments('a(b(c))e'), ['a(b(c))', 'e'])
  assert.deepEqual(breakSegments('x[y(z)]w'), ['x[y(z)]', 'w'])
  assert.deepEqual(breakSegments('x{y}w'), ['x{y}', 'w'])
  assert.deepEqual(breakSegments('a(b)}c'), ['a(b)}', 'c'])
})
