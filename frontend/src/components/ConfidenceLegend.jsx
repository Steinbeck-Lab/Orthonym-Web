import { useEffect, useRef, useState } from 'react'

// The confidence key, as a LADDER.
//
// Three redesigns got here, and the reasoning matters because the obvious
// versions are all worse:
//
//   1. It began as the results panel's empty state, which put the product's
//      most important explanation in the one place guaranteed to disappear
//      the moment you had names to read.
//   2. Then a five-column band of small specimens above the footer. Correct
//      information, no shape: five equal cells reading left to right say
//      nothing about the thing they describe.
//   3. This. The five tiers are not five categories -- they are ONE ORDERED
//      LADDER, from a verified Preferred IUPAC Name down to an input that
//      could not be read. So the band is drawn as a descent: each rung sits
//      lower than the one before it, numbered 01 to 05, with the specimen at
//      a scale you can actually read. The layout carries the meaning, which
//      is the only kind of decoration worth the pixels.
//
// The hard constraint is what makes it interesting: confidence in STITCH is
// MONOCHROME, always (DESIGN.md's one-accent rule -- the crimson never
// touches a tier). So the hierarchy here is built from scale, rhythm, weight
// and motion instead of colour, and every specimen is the exact rule a real
// result carries.

const TIERS = [
  // `label` is the word the interface actually uses next to a name, so it is
  // the label here too -- a key should teach the vocabulary you will meet,
  // not a second longer one. The full tier names live on the result tiles.
  //
  // One line each, deliberately, and every one measured at the real column
  // width -- the tallest rung sets the band's height, so a single sentence
  // wrapping to two lines costs the whole band 20px. The bodies were three
  // lines apiece (259px); these say no less. Progressive disclosure was the other option and it
  // is worse here: it would put reference text behind a hover, which is not
  // reachable by touch and reserves space it may never use.
  {
    key: 'pin',
    ordinal: '01',
    label: 'PIN',
    body: 'Verified, and the preferred name.',
  },
  {
    key: 'fallback',
    ordinal: '02',
    label: 'FALLBACK',
    body: 'Verified, not the preferred one.',
  },
  {
    // "Could not confirm" and NOT "verification did not run", because it did.
    // openstout_service calls _roundtrip_check for every named result --
    // pin, fallback and best_effort alike -- and best-effort mode has no
    // bearing on whether OPSIN is consulted. What the mode changes is
    // whether a name the check failed to confirm may be SHOWN at all; with
    // it off, that molecule comes back as an abstain instead.
    // A previous line here read "Best-effort mode only; unconfirmed.", which
    // was read (reasonably) as "OPSIN verification doesn't run in this
    // mode". The mode link belongs on a result, where Tile.jsx states it,
    // not compressed into a tier definition where it changes its meaning.
    key: 'best-effort',
    ordinal: '03',
    label: 'UNVERIFIED',
    body: 'OPSIN could not confirm it.',
  },
  {
    key: 'abstain',
    ordinal: '04',
    label: 'NO NAME',
    body: 'The engine refused to guess.',
  },
  {
    // Not only an unreadable SMILES: RDKit failing to parse gives this status
    // (openstout_service.py), and so does a naming exception on a batch row
    // ("Naming failed: ...", tasks.py). The old line said "The SMILES could
    // not be read", which was false for the second case.
    key: 'error',
    ordinal: '05',
    label: 'BAD INPUT',
    body: 'Unreadable input, or naming failed.',
  },
]

// The specimens, drawn as SVG rather than CSS borders.
//
// Not for looks: a stroke can be DRAWN. Each rung's mark draws itself from
// left to right when the rung is hovered or focused, and a dashed rule
// drawing dash by dash is the clearest possible way to show what "dashed"
// means in this vocabulary. It is the same stitching motif as the footer's
// join and the nav's arriving dot, which makes it the system's signature
// rather than a one-off flourish.
//
// The dasharray patterns ARE the grammar: solid pair (verified PIN), dashed
// (verified fallback), dotted (unverified), one faint line (abstain), and a
// struck pair (error).
function Specimen({ tier }) {
  const common = {
    className: 'rung__stroke',
    strokeLinecap: 'butt',
    vectorEffect: 'non-scaling-stroke',
  }
  return (
    <svg
      className="rung__specimen"
      viewBox="0 0 200 24"
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      {tier === 'pin' && (
        <>
          <line {...common} x1="0" y1="9" x2="200" y2="9" strokeWidth="2" />
          <line {...common} x1="0" y1="15" x2="200" y2="15" strokeWidth="2" />
        </>
      )}
      {tier === 'fallback' && (
        <line {...common} x1="0" y1="12" x2="200" y2="12" strokeWidth="2" strokeDasharray="10 7" />
      )}
      {tier === 'best-effort' && (
        <line {...common} x1="0" y1="12" x2="200" y2="12" strokeWidth="2" strokeDasharray="2 6" />
      )}
      {tier === 'abstain' && (
        <line {...common} x1="0" y1="12" x2="200" y2="12" strokeWidth="1" />
      )}
      {tier === 'error' && (
        <>
          <line {...common} x1="0" y1="8" x2="200" y2="8" strokeWidth="1.5" />
          <line {...common} x1="0" y1="16" x2="200" y2="16" strokeWidth="1.5" />
          {/* Struck with VERTICAL ticks, not a diagonal. The specimen is
              stretched horizontally (preserveAspectRatio="none"), which
              flattens any diagonal into a near-horizontal line -- measured:
              the first version's strike read as a third wonky rule and made
              this mark ambiguous with the PIN's double rule. A vertical line
              survives the stretch exactly, because non-scaling-stroke keeps
              its width and the stretch only moves its x. */}
          {[64, 100, 136].map((x) => (
            <line {...common} key={x} x1={x} y1="4" x2={x} y2="20" strokeWidth="1.5" />
          ))}
        </>
      )}
    </svg>
  )
}

export default function ConfidenceLegend() {
  // The band builds itself rung by rung the first time it comes into view.
  // An IntersectionObserver rather than an on-load animation: this sits at
  // the foot of a long page, so animating on load would play it where nobody
  // is looking, which is decoration. Once revealed it stays revealed --
  // re-animating on every scroll past is a nervous tic, not delight.
  const bandRef = useRef(null)
  const [revealed, setRevealed] = useState(false)

  useEffect(() => {
    const band = bandRef.current
    if (!band) return undefined
    if (typeof IntersectionObserver === 'undefined') {
      // No observer (very old engine, or a test environment): show it. The
      // reveal is the optional part; the key itself is not.
      setRevealed(true)
      return undefined
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setRevealed(true)
          observer.disconnect()
        }
      },
      { rootMargin: '0px 0px -12% 0px' }
    )
    observer.observe(band)
    return () => observer.disconnect()
  }, [])

  return (
    <aside
      ref={bandRef}
      className={revealed ? 'key-band key-band--in' : 'key-band'}
      aria-label="What the confidence marks mean"
    >
      {/* A caption, not a headline. A display-size title plus a two-line lede
          made this box 434px tall to say five short things -- a key earns its
          space by being scannable, not by announcing itself. */}
      <p className="key-band__caption">
        The mark under every name, strongest first
      </p>

      <ol className="key-band__rungs">
        {TIERS.map((tier, index) => (
          <li
            className={`rung rung--${tier.key}`}
            key={tier.key}
            /* --i drives both the descent and the reveal stagger, so the
               ladder's shape and its entrance come from the same number. */
            style={{ '--i': index }}
          >
            <span className="rung__ordinal">{tier.ordinal}</span>
            <Specimen tier={tier.key} />
            <h3 className="rung__name">{tier.label}</h3>
            <p className="rung__body">{tier.body}</p>
          </li>
        ))}
      </ol>
    </aside>
  )
}
