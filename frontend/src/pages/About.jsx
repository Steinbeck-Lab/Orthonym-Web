import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { checkHealth } from '../lib/api'
import Icon from '../components/Icon'
import BrushCross from '../components/BrushCross'
import LoopGlyph from '../components/LoopGlyph'
import RoundTripLoop from '../components/RoundTripLoop'
import TierLamp from '../components/TierLamp'
import TierRule from '../components/TierRule'
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
    <div className="status-board">
      <div className="status-board__row">
        {/* THE LAMP reports LIVENESS, not the verdict: the verdict stays in the
            rule beside it and in the words, so colour never carries a health
            claim alone. When nothing answers, the light goes out. */}
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

        {/* Only the words are the live region, so a check reads out the
            state, not the button label and the disclosure with it. */}
        <div className="status-board__text" role="status" aria-live="polite" aria-busy={isChecking}>
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

// Where a name can stop. The four tiers, each drawn as how far round the loop
// its line gets, and each wearing the rule it carries under every name on the
// site. `reach` is in quarters of the loop: station 2 sits at 1/4, station 4 at
// 3/4, and 1 is the loop closed.
const EXITS = [
  {
    status: 'pin',
    name: 'Preferred IUPAC name',
    body: 'Built to the strict rule, and read back clean.',
    where: 'The loop closes on a name from the strict rules.',
    reach: 1,
  },
  {
    status: 'fallback',
    name: 'Fallback',
    body: 'Reads back clean, but its preferred status is not certified.',
    where: 'The loop closes. The strict PIN path did not certify the name.',
    reach: 1,
  },
  {
    status: 'best_effort',
    name: 'Best effort',
    body: 'The general engine named it; the read-back verdict is shown under it.',
    // The glyph stays open (reach 0.75): best effort reads back too, but it is
    // not one of the two verified tiers, and the line says that, not a failure.
    where: 'The loop stays open: best effort is not a verified tier.',
    reach: 0.75,
  },
  {
    status: 'abstain',
    name: 'No name',
    body: 'The engine declined rather than guess.',
    where: 'The line stops at step 2.',
    reach: 0.25,
  },
]

const PATTERN = { pin: 'pin', fallback: 'fallback', best_effort: 'best', abstain: 'abstain' }

// The three ways in, each shown by which part of the loop it runs.
const WAYS = [
  {
    to: '/',
    title: 'Translate',
    body: 'Paste, upload or draw a structure. With OPSIN verify on (the default) it runs the whole loop, and every result gets its mark.',
    nodes: [1, 2, 3, 4],
  },
  {
    to: '/from-name',
    title: 'Name → Structure',
    body: 'Type a name and get the structure. This is step 3 on its own, run by OPSIN rather than the engine backwards, because reading a name is a different job from writing one.',
    nodes: [3],
  },
  {
    to: '/explain',
    title: 'Explain',
    body: 'Takes a name apart as OPSIN reads it, whether Orthonym wrote it or you typed it, and maps each part to the atoms it names. Notation that names no atoms of its own is marked as notation; a part it cannot place is marked as unmapped.',
    nodes: [2, 3],
  },
]

// Who does each step. Real marks where the project publishes one.
const CREDITS = [
  {
    // No link: the engine's repository is private (see Details).
    name: 'Orthonym rule engine',
    role: 'Writes the name at step 2, from fixed naming rules. No model, no training data.',
    nodes: [2],
  },
  {
    name: 'OPSIN',
    role: 'Reads the name back into a structure at step 3. Every read-back on this site is its answer, not ours.',
    href: 'https://github.com/dan2097/opsin',
    nodes: [3],
  },
  {
    name: 'RDKit',
    role: 'Reads the structure at step 1, and compares the two structures at step 4 by InChIKey (by canonical SMILES when no key can be computed). It also draws them if CDK is unavailable.',
    href: 'https://www.rdkit.org/',
    logo: '/logos/rdkit.png',
    nodes: [1, 4],
  },
  {
    // backend/app/depiction.py: CDK first, RDKit only as the fallback.
    // Logo: https://cdk.github.io/img/logo.png, trimmed and scaled to 96px.
    name: 'CDK',
    role: 'Draws both structures you compare, and marks a stereocentre the input leaves undefined as (?).',
    href: 'https://cdk.github.io/',
    logo: '/logos/cdk.png',
    nodes: [1, 3],
  },
]

function About() {
  return (
    <main className="about">
      {/* The masthead and the loop share one card: the page opens on the
          engine at work, not on a paragraph about it. */}
      <section className="about-hero card" aria-labelledby="about-title">
        <header className="about-hero__head">
          <img
            className="about-hero__logo"
            src="/logos/ORTHONYM.png"
            alt="Orthonym"
            width={1332}
            height={294}
          />
          <h1 className="about-hero__title" id="about-title">
            How a name is built, and checked
          </h1>
          <p className="about-hero__lede">
            The engine writes the name by rule. OPSIN, which never sees the structure, reads it back.
            If the same structure comes back and the name holds a verified tier, the loop closes.
          </p>
        </header>
        <RoundTripLoop />
      </section>

      <section className="exits card" id="key" aria-labelledby="exits-title">
        <div className="about-section__head">
          <h2 className="about-section__title" id="exits-title">
            Where a name can stop
          </h2>
          <p className="about-section__note">
            Every result the engine returns ends at one of these four. A fifth mark, a struck ring,
            means no name could be produced: the input could not be read, or naming failed.
          </p>
        </div>
        <ul className="exits__list" role="list">
          {EXITS.map((e) => (
            <li className="exit" key={e.status}>
              <LoopGlyph
                reach={e.reach}
                pattern={PATTERN[e.status]}
                nodes={[1, 2, 3, 4].slice(0, Math.min(4, Math.round(e.reach * 4) + 1))}
              />
              <p className="exit__name">
                <TierLamp status={e.status} />
                <span>{e.name}</span>
              </p>
              <TierRule status={e.status} className="exit__rule" />
              <p className="exit__body">{e.body}</p>
              <p className="exit__where">{e.where}</p>
            </li>
          ))}
        </ul>
      </section>

      <div className="about-pair">
        <section className="card about-list" aria-labelledby="ways-title">
          <div className="about-section__head">
            <h2 className="about-section__title" id="ways-title">
              Three ways onto the loop
            </h2>
            <p className="about-section__note">Each runs part of the same loop.</p>
          </div>
          <ul className="about-list__rows" role="list">
            {WAYS.map((w) => (
              <li className="about-list__row" key={w.to}>
                <LoopGlyph nodes={w.nodes} />
                <div>
                  <h3 className="about-list__name">
                    <Link to={w.to}>{w.title}</Link>
                  </h3>
                  <p className="about-list__body">{w.body}</p>
                </div>
              </li>
            ))}
          </ul>
        </section>

        <section className="card about-list" aria-labelledby="credits-title">
          <div className="about-section__head">
            <h2 className="about-section__title" id="credits-title">
              Who does each step
            </h2>
            <p className="about-section__note">None of it is ours alone.</p>
          </div>
          <ul className="about-list__rows" role="list">
            {CREDITS.map((c) => (
              <li className="about-list__row" key={c.name}>
                <LoopGlyph nodes={c.nodes} />
                <div>
                  <h3 className="about-list__name">
                    {c.href ? (
                      <a href={c.href} target="_blank" rel="noopener noreferrer">
                        {c.logo && <img className="about-list__logo" src={c.logo} alt="" />}
                        {c.name}
                      </a>
                    ) : (
                      c.name
                    )}
                  </h3>
                  <p className="about-list__body">{c.role}</p>
                </div>
              </li>
            ))}
          </ul>
        </section>
      </div>

      {/* WHO MADE IT. A partnership is not a dependency, so it is not a row in
          the credits. The join is BrushCross, a painted mark at signature
          scale, not the footer's hairline cross. */}
      <section className="collab-card card" aria-labelledby="collab-title">
        <h2 className="about-section__title collab-card__title" id="collab-title">
          Made together
        </h2>
        <div className="collab">
          <a
            className="collab__org"
            href="https://www.beilstein-institut.de/en/"
            target="_blank"
            rel="noopener noreferrer"
          >
            <img src="/Logo_Beilstein_schmal_RGB.svg" alt="Beilstein-Institut" width={876} height={202} />
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
      </section>

      <section className="details card" aria-labelledby="details-title">
        <h2 className="about-section__title" id="details-title">
          Details
        </h2>
        <dl className="details__list">
          <div className="details__row">
            <dt>Engine</dt>
            <dd>Orthonym v1.0.0: deterministic and rule-based, not a language model.</dd>
          </div>
          <div className="details__row">
            <dt>Method</dt>
            <dd>Rule-based naming engine.</dd>
          </div>
          <div className="details__row">
            <dt>Source</dt>
            {/* No link: the upstream repository is private and answers 404
                to an anonymous visitor, and a link to the source would
                promise a target a reader cannot open. Terms.jsx and
                Navigation.jsx carry the same fact; the three move together. */}
            <dd>
              MIT licence. Vendored as a source snapshot; the upstream repository is not yet public.
            </dd>
          </div>
          <div className="details__row">
            <dt>Made by</dt>
            <dd>Kohulan Rajan</dd>
          </div>
          <div className="details__row details__row--status">
            <dt>Right now</dt>
            <dd>
              <ServiceStatus />
            </dd>
          </div>
        </dl>
      </section>
    </main>
  )
}

export default About
