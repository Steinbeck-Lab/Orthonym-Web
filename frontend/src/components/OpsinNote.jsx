import { useDisclosure } from '../lib/useDisclosure'

// THE OPSIN NOTE: the same notch-and-drawer chrome ConfidenceLegend.jsx
// wears on Home (`.info`, `.info__notch`, `.info__drawer`, `.info__panel`,
// the bulb, the flip, the fillets -- all promoted to App.css on 2026-09-04
// for exactly this reuse; the state/effect mechanism behind it is shared
// too, via `lib/useDisclosure.js`), carrying different content. Read that
// hook for the mechanism's own long-form reasoning; this file only adds
// what belongs on THIS page.
//
// /from-name computes no confidence tier -- OPSIN's parse either succeeds
// or it does not -- so there is no rung ladder here, only four short
// paragraphs of prose explaining how a typed name becomes a structure, and
// the citation for the parser doing the work.
//
// No `openToSide`: unlike Home's input card, which sits centred and alone
// on an empty page with real space to its right, this page's input card
// (`.from-name-panel`) is already the left third of an always-two-column
// `.workspace` grid -- the results card is right there beside it from the
// first paint, whether or not it holds anything yet. There is no empty
// gutter to open a side panel into, so the drawer only ever opens downward,
// the same as Home's own bottom mode once results share its row.
export default function OpsinNote() {
  const { open, panelId, rootRef, toggle, classes } = useDisclosure()

  return (
    <div className={classes.join(' ')} ref={rootRef}>
      {/* THE NOTCH, unchanged from ConfidenceLegend.jsx's own copy: the
          header's shape, carved out of the bottom of THIS card by the same
          pair of concave fillets, mirrored from .notch__wing in App.css. */}
      <button
        type="button"
        className="info__notch"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={toggle}
      >
        <span className="notch__wing notch__wing--left" aria-hidden="true" />
        <span className="notch__wing notch__wing--right" aria-hidden="true" />
        <span className="info__bulb" aria-hidden="true">
          <span className="info__bulb-glow" />
          <span className="info__bulb-dot" />
        </span>
        <span className="info__notch-label">Info</span>
      </button>

      <div
        className="info__drawer"
        id={panelId}
        role="group"
        aria-label="How OPSIN reads a name"
      >
        <div className="info__panel">
          {/* `.prose` (App.css), not `.prose-sm`: this is running explanatory
              copy, the same register About.jsx's own paragraphs use, and
              its `> * + *` rule is what gives four independent <p>s their
              spacing without a new class just for this drawer. */}
          <div className="prose">
            <p>
              The name goes straight to OPSIN. This direction runs through OPSIN, not
              the Orthonym engine &mdash; that engine turns structures into names;
              going the other way needs a name-to-structure parser instead.
            </p>
            <p>
              OPSIN parses, it does not look up. It works the structure out from the
              nomenclature grammar itself, so it resolves systematic names that appear
              in no database &mdash; a correct IUPAC name for an obscure molecule still
              works, even one nobody has typed here before.
            </p>
            <p>
              What comes back is a SMILES string. RDKit then derives the canonical
              SMILES, the InChI and the InChIKey from it, and generates the 2D
              coordinates the SDF download carries.
            </p>
            <p>
              A name OPSIN cannot resolve is refused, not guessed. Trade names, typos
              and ambiguous fragments come back as &ldquo;Could not parse this name via
              OPSIN&rdquo; rather than a nearest match &mdash; the same honesty the
              confidence tiers exist for on the naming side.
            </p>
            <p>
              OPSIN 2.9.0. Lowe, D. M.; Corbett, P. T.; Murray-Rust, P.; Glen, R. C.
              &ldquo;Chemical Name to Structure: OPSIN, an Open Source
              Solution.&rdquo; <i>Journal of Chemical Information and Modeling</i>{' '}
              <b>2011</b>, <i>51</i> (3), 739&ndash;753.{' '}
              <a
                className="about-link"
                href="https://doi.org/10.1021/ci100384d"
                target="_blank"
                rel="noopener noreferrer"
              >
                doi.org/10.1021/ci100384d
              </a>
              .
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
