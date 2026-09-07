import { useCallback, useEffect, useState } from 'react'
import { checkHealth } from '../lib/api'
import Icon from '../components/Icon'
import ChartedName from '../components/ChartedName'
import BrushCross from '../components/BrushCross'
import RoundTripProof from '../components/RoundTripProof'
import ThreadCard from '../components/ThreadCard'
import useReducedMotion from '../lib/useReducedMotion'
import useReveal from '../lib/useReveal'
import './About.css'

// Four phases, not three. `degraded` is the one that was missing when this
// board was still its own /health page, and its absence was a lie the page
// told out loud: GET /api/health answers 200 with
// {"status":"DEGRADED","opsin":"no worker has a live JVM"} whenever no worker
// can verify a name, and the old page rendered that as "Reachable & healthy"
// under its single strongest positive mark, because it branched on whether
// the FETCH resolved and never read the payload. Measured live, not
// theorised. A status board that asserts health it did not check is the same
// failure the product exists to avoid, in a smaller frame.
const STATE_LABEL = {
  checking: 'Checking…',
  healthy: 'Reachable & healthy',
  degraded: 'Reachable, but degraded',
  unreachable: 'Unreachable',
}

// The mark grammar is carried over byte-for-byte: checking = three shimmering
// hairline dashes, reachable = ONE solid 2px ink rule, degraded = that same
// rule at a shorter measure, unreachable = the struck pair. Reachable is
// deliberately NOT the double rule -- paired ink lines already mean a verified
// PIN in this system, and a state signal that borrows another state's shape
// carries no information at all. No hue is ever used for health.
function ServiceStatus() {
  const [phase, setPhase] = useState('checking')
  const [raw, setRaw] = useState(null)
  const [error, setError] = useState(null)
  const [checkedAt, setCheckedAt] = useState(null)

  const runCheck = useCallback(() => {
    setPhase('checking')
    checkHealth()
      .then((data) => {
        setRaw(data)
        setError(null)
        setCheckedAt(new Date())
        // Read the payload, not merely the fact that one arrived. Anything
        // other than "OK" is degraded -- the fail-closed direction for a claim
        // about health.
        setPhase(data?.status === 'OK' ? 'healthy' : 'degraded')
      })
      .catch((err) => {
        setRaw(null)
        setError(err?.message || 'network error')
        setCheckedAt(new Date())
        setPhase('unreachable')
      })
  }, [])

  useEffect(() => {
    runCheck()
  }, [runCheck])

  const isChecking = phase === 'checking'
  const rawDisplay = isChecking ? '—' : raw !== null ? JSON.stringify(raw, null, 2) : error

  return (
    <div className="status-board" role="status" aria-live="polite" aria-busy={isChecking}>
      <div className="status-board__row">
        {/* THE LAMP. A live-status light, the way a status page shows one --
            and it reports LIVENESS, not the verdict: it says a real check is
            running and how recently it answered. The verdict stays where it
            was, in the rule beside it and in the words, so colour is never the
            only thing carrying a health claim (DESIGN.md's rule, kept). The
            one state it does encode by itself is the honest one: when nothing
            answers, the light goes out. */}
        <span className={`status-lamp status-lamp--${phase}`} aria-hidden="true">
          <span className="status-lamp__glow" />
          <span className="status-lamp__core" />
        </span>

        <span className="status-board__mark" aria-hidden="true">
          {phase === 'checking' && (
            <span className="status-board__pending">
              <span className="status-board__pending-dash" />
              <span className="status-board__pending-dash" />
              <span className="status-board__pending-dash" />
            </span>
          )}
          {phase === 'healthy' && <span className="status-board__fill" />}
          {phase === 'degraded' && (
            <span className="status-board__fill status-board__fill--partial" />
          )}
          {phase === 'unreachable' && (
            <span className="status-board__snip-wrap">
              <span className="status-board__snip" />
              <span className="status-board__snip" />
            </span>
          )}
        </span>

        <div className="status-board__text">
          <p className="status-board__label">{STATE_LABEL[phase]}</p>
          {phase === 'degraded' && raw?.opsin && (
            <p className="prose-sm status-board__reason">
              {raw.opsin}. Naming endpoints answer 503 until a worker reports one.
            </p>
          )}
          <p className="status-board__meta">
            {checkedAt ? `Checked ${checkedAt.toLocaleString()}` : '—'}
          </p>
        </div>

        <button type="button" className="btn btn--sm" onClick={runCheck} disabled={isChecking}>
          <Icon name="refresh" />
          {isChecking ? 'Checking…' : 'Check again'}
        </button>
      </div>

      <details className="status-board__details">
        <summary>Raw response</summary>
        <pre className="status-board__raw">{rawDisplay}</pre>
      </details>
    </div>
  )
}

// A sheet of the pattern. Every section is a numbered sheet with a title
// block, because that is how a chart is bound: the reader always knows which
// sheet they are on and what it is for.
function Sheet({ id, index, title, note, children, reduced }) {
  const [ref, shown] = useReveal({ reduced })
  return (
    <section
      id={id}
      ref={ref}
      className={`sheet${shown ? ' is-shown' : ''}`}
      aria-labelledby={`${id}-title`}
    >
      <header className="sheet__head">
        <span className="sheet__index" aria-hidden="true">
          {index}
        </span>
        <h2 className="sheet__title" id={`${id}-title`}>
          {title}
        </h2>
        {note && <p className="sheet__note">{note}</p>}
      </header>
      <div className="sheet__body">{children}</div>
    </section>
  )
}

// The four tier marks, drawn as a pattern chart's symbol key.
//
// This is the single best fit between the two worlds and the reason the world
// works at all: Orthonym's confidence tiers were ALREADY a set of monochrome
// line symbols with fixed meanings -- double rule, dashed, dotted, faint --
// which is precisely what a chart's key is. Nothing was invented to make them
// fit. A reader who learns the key here recognises the same mark under a name
// on every other page, which is what the product needs and what a key is for.
const KEY_ROWS = [
  {
    mark: 'pin',
    name: 'Preferred IUPAC Name',
    body: 'Worked to the strict rule, and read back clean.',
  },
  {
    mark: 'fallback',
    name: 'Fallback',
    body: 'Reads back clean, but is not the preferred name.',
  },
  {
    mark: 'best',
    name: 'Best effort',
    body: 'The engine worked it. OPSIN could not confirm it.',
  },
  {
    mark: 'abstain',
    name: 'Left unworked',
    body: 'No name — it declined rather than guess.',
  },
]

// The thread list. Real marks where the project publishes one; a typographic
// lockup where it does not. See ThreadCard for why that distinction is drawn
// rather than smoothed over.
const THREADS = [
  {
    code: '01',
    name: 'OPSIN',
    role: 'Reads a name back into a structure. Every verification on this site is its answer, not ours.',
    href: 'https://github.com/dan2097/opsin',
  },
  {
    code: '02',
    name: 'RDKit',
    role: 'Molecular perception, and the drawings.',
    logo: '/logos/rdkit.png',
    alt: 'RDKit',
    href: 'https://www.rdkit.org/',
  },
  {
    code: '03',
    name: 'IUPAC Blue Book',
    role: 'The 2013 recommendations — the rules the engine works to, not a style of its own.',
    href: 'https://iupac.org/what-we-do/books/bluebook/',
  },
]

// The three routes, written as a pattern's working instructions: what you do,
// in order, on each. Row language rather than paragraph language, because a
// chart tells you to work a row, not about working rows.
const ROWS = [
  {
    n: 'I',
    title: 'Translate',
    body: 'Paste, upload or draw a structure. The engine works the name and marks it with one of the four symbols opposite.',
  },
  {
    n: 'II',
    title: 'Name → Structure',
    body: 'The reverse. This one runs on OPSIN rather than the engine backwards, because reading a name is a different craft from writing one.',
  },
  {
    n: 'III',
    title: 'Explain',
    body: 'Unpicks a finished name into the parts it was worked from, each mapped to the atoms it covers. Anything it cannot place, it says so.',
  },
]

// About Orthonym, worked as a pattern chart.
//
// The world was chosen by the owner from a hand of four (2026-09-06) and it is
// the one that fits what the product does: a name worked from parts, in a
// fixed order, to a written rule. The footer already sews itself shut and the
// nav pulls a thread tight on arrival, so the page is not importing a metaphor
// -- it is finally speaking the one the site already had.
//
// The page had been rebuilt twice before as a document in cards and failed on
// four counts at once (too plain, too little imagery, wrong order, too
// sparse), so this replaces the composition rather than passing over it again.
//
// The mapping is not decoration laid over content; every region of a real
// chart already had a tenant here:
//   the KEY      <- the four confidence tiers, already a set of line symbols
//   the THREADS  <- the dependency credits, with their real marks as swatches
//   the ROWS     <- the three routes, as working instructions
//   the PIECE    <- the live round-trip, which is the finished thing itself
//   the GAUGE    <- engine, version, licence, author, and whether it is up
function About() {
  const reduced = useReducedMotion()

  return (
    <>
      {/* The pattern's cover sheet. */}
      <section className="chart-cover" aria-label="Introduction">
        <div className="chart-cover__plate">
          {/* The name first, worked across the full measure. It is the
              masthead of the pattern, so it leads. */}
          <ChartedName />

          <h1 className="chart-cover__title">How a name is worked</h1>
          <p className="chart-cover__lede">
            Orthonym builds an IUPAC name the way a chart builds a piece: from named parts, in a
            fixed order, to a written rule. Nothing is guessed, and the finished work is checked
            against the pattern before you are shown it.
          </p>

          <dl className="chart-cover__gauge">
            <div>
              <dt>Worked to</dt>
              <dd>IUPAC 2013</dd>
            </div>
            <div>
              <dt>Engine</dt>
              <dd>Orthonym v1.0.0</dd>
            </div>
            <div>
              <dt>Method</dt>
              <dd>Rule-based</dd>
            </div>
          </dl>
        </div>
      </section>

      <main className="chart">
        {/* THE PIECE — the live proof, worked in front of the reader. */}
        <Sheet
          id="piece"
          index="Sheet 1"
          title="The finished piece"
          note="Worked live, on this server, while you watch."
          reduced={reduced}
        >
          <RoundTripProof />
        </Sheet>

        {/* THE KEY — the symbols, which the product already had. */}
        <Sheet
          id="key"
          index="Sheet 2"
          title="Key"
          note="Every name on this site carries one of these four marks."
          reduced={reduced}
        >
          <dl className="key">
            {KEY_ROWS.map((row) => (
              <div className="key__row" key={row.mark}>
                <dt>
                  <span className={`key__mark key__mark--${row.mark}`} aria-hidden="true" />
                  <span className="key__name">{row.name}</span>
                </dt>
                <dd>{row.body}</dd>
              </div>
            ))}
          </dl>
        </Sheet>

        {/* THE ROWS — the three routes as working instructions. */}
        <Sheet
          id="rows"
          index="Sheet 3"
          title="Working instructions"
          note="Three ways in. The same engine behind each."
          reduced={reduced}
        >
          <ol className="rows" role="list">
            {ROWS.map((row) => (
              <li className="row" key={row.n}>
                <span className="row__n" aria-hidden="true">
                  {row.n}
                </span>
                <h3 className="row__title">{row.title}</h3>
                <p className="row__body">{row.body}</p>
              </li>
            ))}
          </ol>
        </Sheet>

        {/* THE THREADS — the credits, where a floss list belongs. */}
        <Sheet
          id="threads"
          index="Sheet 4"
          title="Threads"
          note="What the work is made from. None of it is ours alone."
          reduced={reduced}
        >
          <ul className="threads" role="list">
            {THREADS.map((t) => (
              <ThreadCard key={t.code} {...t} />
            ))}
          </ul>
        </Sheet>

        {/* WHO WORKED IT. The two institutions get their own sheet rather than
            a row in the thread list: a partnership is not a dependency, and
            filing it as one undersold it.
            The join is BrushCross -- a painted mark at signature scale, NOT the
            footer's sewn hairline. They are deliberately different: the
            footer's × is punctuation inside a sentence, this one is the thing
            the sheet is about. Same letter, different drawing, different job. */}
        <Sheet
          id="collaboration"
          index="Sheet 5"
          title="Worked together"
          reduced={reduced}
        >
          <div className="collab">
            <a
              className="collab__org"
              href="https://www.beilstein-institut.de/en/"
              target="_blank"
              rel="noopener noreferrer"
            >
              <img
                src="/Logo_Beilstein_schmal_RGB.svg"
                alt="Beilstein-Institut"
                width={876}
                height={202}
              />
            </a>

            <span className="sr-only">and</span>
            <BrushCross className="collab__x" />

            <a
              className="collab__org"
              href="https://cheminf.uni-jena.de"
              target="_blank"
              rel="noopener noreferrer"
            >
              <img
                src="/logos/steinbeck.png"
                alt="Natural Products Cheminformatics, Friedrich Schiller University Jena — the Steinbeck Lab"
                width={1666}
                height={400}
              />
            </a>
          </div>

          <p className="collab__line">An official collaboration for open science.</p>
        </Sheet>

        {/* THE GAUGE — the maker's block that closes a pattern. */}
        <Sheet id="gauge" index="Sheet 6" title="Maker's notes" reduced={reduced}>
          <dl className="gauge">
            <div className="gauge__row">
              <dt>Engine</dt>
              <dd>Orthonym v1.0.0 — deterministic and rule-based, not a language model.</dd>
            </div>
            <div className="gauge__row">
              <dt>Source</dt>
              {/* No link: the upstream repository is private and answers 404
                  to an anonymous visitor, and "Read the pattern itself"
                  promises a target a reader cannot open. Terms.jsx and
                  Navigation.jsx carry the same fact; the three move
                  together. */}
              <dd>
                MIT licence. Vendored as a source snapshot; the upstream repository is not yet
                public.
              </dd>
            </div>
            <div className="gauge__row">
              <dt>Worked by</dt>
              <dd>Kohulan Rajan</dd>
            </div>
            <div className="gauge__row gauge__row--status">
              <dt>Right now</dt>
              <dd>
                <ServiceStatus />
              </dd>
            </div>
          </dl>
        </Sheet>
      </main>
    </>
  )
}

export default About
