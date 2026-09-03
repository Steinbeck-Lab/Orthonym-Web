import { useEffect, useId, useRef, useState } from 'react'

// The confidence key, as a DRAWER behind an INFO notch on the input card.
//
// Four shapes got here, and the reasoning matters because the obvious
// versions are all worse:
//
//   1. It began as the results panel's empty state, which put the product's
//      most important explanation in the one place guaranteed to disappear
//      the moment you had names to read.
//   2. Then a five-column band of small specimens above the footer. Correct
//      information, no shape.
//   3. Then a five-column ladder, still always on. It was honest and it was
//      read once: after that it spent 135px of a one-screen page, every
//      visit, on a reference nobody was looking at any more. Its width was
//      also its own measure rather than anything else on the page, so it
//      floated free of the card it describes.
//   4. This. A notch on the input card, and the key behind it. The panel is
//      the CARD's width because it is part of the card, it costs 34px at
//      rest instead of 135, and a reference you can put away is a reference
//      you can also open again, which the always-on version could not offer.
//
// The five tiers are ONE ORDERED LADDER, from a verified Preferred IUPAC
// Name down to an input that could not be read, so they are drawn as five
// rows, strongest first: the vertical order IS the descent, and it no longer
// needs the staircase offset the five-column version used to fake one.
//
// The hard constraint is what makes it interesting: confidence in STITCH is
// MONOCHROME, always (DESIGN.md's one-accent rule, the crimson never touches
// a tier). So the hierarchy here is built from scale, rhythm, weight and
// motion instead of colour, and every specimen is the exact rule a real
// result carries.

const TIERS = [
  // `label` is the word the interface actually uses next to a name, so it is
  // the label here too: a key should teach the vocabulary you will meet, not
  // a second longer one. The full tier names live on the result tiles.
  //
  // TWO lines each: what the tier IS, then how it got that way. The one-line
  // version fitted, and it left every reader who did not already know the
  // engine to guess at the mechanism -- "Verified" by what? The detail line
  // is where the round-trip, the rule set and the abstain's formula get
  // named, and it costs 50px across all five because the space it uses was
  // empty panel on the right.
  {
    key: 'pin',
    ordinal: '01',
    label: 'PIN',
    body: 'Verified, and the preferred name.',
    detail: 'OPSIN read the name back and got your structure.',
  },
  {
    key: 'fallback',
    ordinal: '02',
    label: 'FALLBACK',
    body: 'Verified, but not the preferred name.',
    detail: 'Correct by the general rules, not the strict ones.',
  },
  {
    // "Could not confirm" and NOT "verification did not run", because it did.
    // openstout_service calls _roundtrip_check for every named result: pin,
    // fallback and best_effort alike, and best-effort mode has no bearing on
    // whether OPSIN is consulted. What the mode changes is whether a name the
    // check failed to confirm may be SHOWN at all; with it off, that molecule
    // comes back as an abstain instead.
    // A previous line here read "Best-effort mode only; unconfirmed.", which
    // was read (reasonably) as "OPSIN verification doesn't run in this mode".
    // The mode link belongs on a result, where Tile.jsx states it, not
    // compressed into a tier definition where it changes its meaning.
    key: 'best-effort',
    ordinal: '03',
    label: 'UNVERIFIED',
    body: 'A real name OPSIN could not confirm.',
    // "The check ran" is the load-bearing half of this line, for the reason
    // in the comment above.
    detail: 'The check ran and failed. Best-effort mode only.',
  },
  {
    key: 'abstain',
    ordinal: '04',
    label: 'NO NAME',
    body: 'The engine declined rather than guess.',
    // Only an abstain carries a formula (openstout_service.py sets it
    // nowhere else), which is exactly why it is worth saying here.
    detail: 'A molecular formula stands in for the name.',
  },
  {
    // Not only an unreadable SMILES: RDKit failing to parse gives this status
    // (openstout_service.py), and so does a naming exception on a batch row
    // ("Naming failed: ...", tasks.py). The old line said "The SMILES could
    // not be read", which was false for the second case.
    key: 'error',
    ordinal: '05',
    label: 'BAD INPUT',
    body: 'The input could not be named.',
    detail: 'RDKit refused it, or naming failed part-way.',
  },
]

// The specimens, drawn as SVG rather than CSS borders.
//
// Not for looks: a stroke can be DRAWN. Each rung's mark draws itself from
// left to right as the drawer opens, and a dashed rule drawing dash by dash
// is the clearest possible way to show what "dashed" means in this
// vocabulary. It is the same stitching motif as the footer's join, the nav's
// arriving dot and the drop zone's running seam, which makes it the system's
// signature rather than a one-off flourish.
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
      {tier === 'abstain' && <line {...common} x1="0" y1="12" x2="200" y2="12" strokeWidth="1" />}
      {tier === 'error' && (
        <>
          <line {...common} x1="0" y1="8" x2="200" y2="8" strokeWidth="1.5" />
          <line {...common} x1="0" y1="16" x2="200" y2="16" strokeWidth="1.5" />
          {/* Struck with VERTICAL ticks, not a diagonal. The specimen is
              stretched horizontally (preserveAspectRatio="none"), which
              flattens any diagonal into a near-horizontal line: measured,
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

export default function ConfidenceLegend({ openToSide = false, onOpenChange }) {
  const [open, setOpen] = useState(false)

  // Report the open state up so the page can move the input card aside to make
  // room for the side bar (owner instruction 2026-09-03: the box may move).
  useEffect(() => {
    onOpenChange?.(open)
  }, [open, onOpenChange])
  // The bulb breathes until the key has been opened ONCE, then goes steady
  // for the rest of the session. Its job is to point out something you have
  // not seen; a lamp that keeps pulsing at someone who has already read the
  // thing is a nervous tic, not a signal.
  const [seen, setSeen] = useState(false)
  const panelId = useId()
  const rootRef = useRef(null)

  // Escape closes it, and so does a click anywhere else. Both are what a
  // disclosure that covers part of a working card owes the person using it:
  // it must never be the reason they cannot get back to the textarea.
  // Bound only while OPEN, so the closed state costs no listeners at all.
  useEffect(() => {
    if (!open) return undefined
    const onKeyDown = (event) => {
      if (event.key === 'Escape') setOpen(false)
    }
    const onPointerDown = (event) => {
      if (!rootRef.current?.contains(event.target)) setOpen(false)
    }
    document.addEventListener('keydown', onKeyDown)
    document.addEventListener('pointerdown', onPointerDown)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      document.removeEventListener('pointerdown', onPointerDown)
    }
  }, [open])

  const classes = ['info']
  if (open) classes.push('info--open')
  if (!seen) classes.push('info--unseen')
  if (openToSide) classes.push('info--side')

  return (
    <div className={classes.join(' ')} ref={rootRef}>
      {/* THE NOTCH, and it is the header's shape rather than a pill: a white
          island welded to the card's bottom edge by a pair of concave
          fillets, mirrored from .notch__wing in App.css. The header carves
          its islands out of the top of the window; this one is carved out of
          the bottom of the card, which is why it reads as part of the card
          and not as something stuck under it. Right-hand side, inset past
          both its own fillet and the card's corner radius. */}
      <button
        type="button"
        className="info__notch"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => {
          setOpen((was) => !was)
          setSeen(true)
        }}
      >
        {/* The header's own fillets, reused rather than mirrored. Both
            islands hang DOWNWARD from their edge -- the header's from the top
            of the window, this one from the bottom of the card -- so the
            concave sweep is the same shape, not a flipped one. An earlier
            version flipped the mask circle to the wing's top corner on the
            theory that a mirrored edge needs a mirrored mask; it welded the
            white to the wrong side and the tab grew a pair of ears. */}
        <span className="notch__wing notch__wing--left" aria-hidden="true" />
        <span className="notch__wing notch__wing--right" aria-hidden="true" />
        {/* The bulb. A crimson lamp that breathes while there is something
            here you have not opened, and goes steady once you have. Crimson
            is legal on it precisely because it is chrome -- an attention
            signal, like the active nav pill -- and it never touches a tier.
            The glow is a separate element so the dot itself stays crisp:
            animating a filter on the dot would blur its own edge. */}
        <span className="info__bulb" aria-hidden="true">
          <span className="info__bulb-glow" />
          <span className="info__bulb-dot" />
        </span>
        <span className="info__notch-label">Info</span>
      </button>

      {/* grid-template-rows 0fr to 1fr is the reveal. A height animation on
          `auto` does not interpolate at all, and a transform would squash the
          type; the grid row is the one technique that opens to the content's
          own height and still animates. The rows inside carry the motion that
          matters: each specimen draws itself, in order. */}
      <div className="info__drawer" id={panelId} role="group" aria-label="Confidence marks">
        <div className="info__panel">
          <p className="info__caption">The mark under every name, strongest first</p>
          <ol className="info__rungs">
            {TIERS.map((tier, index) => (
              <li
                className={`rung rung--${tier.key}`}
                key={tier.key}
                /* --i staggers both the row and the stroke that draws
                   inside it, so the ladder assembles top to bottom from one
                   number. */
                style={{ '--i': index }}
              >
                <span className="rung__ordinal">{tier.ordinal}</span>
                <h3 className="rung__name">{tier.label}</h3>
                <Specimen tier={tier.key} />
                <div className="rung__body">
                  <p className="rung__line">{tier.body}</p>
                  <p className="rung__detail">{tier.detail}</p>
                </div>
              </li>
            ))}
          </ol>
        </div>
      </div>
    </div>
  )
}
