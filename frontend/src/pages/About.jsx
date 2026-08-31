import './About.css'

// About Orthonym: what it is, how it works, its measured accuracy, and the
// verified facts (author, license, acknowledgments) behind the naming
// engine it showcases. Every claim here traces to the engine's own repo
// (pyproject.toml, LICENSE, README) or to this app's own shipped copy —
// nothing invented. The three figures in the spec band below are the same
// measured numbers the accuracy paragraph cites, not new claims. They come
// from Orthonym v1.0.0's README; the earlier four-figure v21.0 split is
// gone because v1.0.0 publishes no per-corpus breakdown to cite.
function About() {
  return (
    <>
      <div className="page-head page-shell">
        <h1 className="page-head__title">About Orthonym</h1>
        <p className="page-head__lede">
          Orthonym is a public showcase for a
          deterministic, rule-based SMILES-to-IUPAC-name engine &mdash; built so visitors can try
          it on real molecules and see exactly how it behaves, including where it succeeds, where
          it falls back, and where it honestly declines to guess.
        </p>
      </div>

      <main className="about-page">
        {/* Orthonym v1.0.0's published figures (its README § Accuracy),
            shown at full size rather than tucked into fine print. v1.0.0
            publishes no per-corpus breakdown, so none is shown. */}
        <section className="about-band" aria-label="Measured accuracy">
          <div className="spec">
            <div className="spec__cell">
              <span className="spec__value">94.8%</span>
              <span className="spec__label">Round-trip exact match</span>
            </div>
            <div className="spec__cell">
              <span className="spec__value">0</span>
              <span className="spec__label">Wrong structures emitted</span>
            </div>
            <div className="spec__cell">
              <span className="spec__value">1,500</span>
              <span className="spec__label">Molecules benchmarked</span>
            </div>
          </div>
        </section>

        <section className="about-band about-band--split" aria-label="How accurate is it">
          <div className="about-band__head">
            <h2>How accurate is it?</h2>
          </div>
          <div className="about-band__body">
            <p className="prose">
              Orthonym&rsquo;s naming engine is rule-based, so the same input always gives the same
              output, and it will tell you when it isn&rsquo;t sure.
            </p>
            <p className="prose">
              The headline metric is round-trip exact match: name the structure, parse the name
              back with OPSIN, and compare canonical identifiers, counting any refusal to name as
              a failure. It is reference-free &mdash; it does not depend on a possibly-noisy
              database name. On a 1,500-molecule benchmark drawn from ChEBI and PubChem,
              Orthonym v1.0.0 scores 94.8% round-trip exact match and emitted 0 wrong
              structures.
            </p>
            <p className="prose">
              That second figure is the design priority: never emit a name for the wrong
              molecule. When a preferred name cannot be built with confidence, the engine drops
              to a less-preferred but still correct systematic name, or abstains &mdash; it does
              not guess. A lower-confidence name is always shown as such, never hidden.
            </p>
          </div>
        </section>

        <section className="about-band about-band--split" aria-label="How it works">
          <div className="about-band__head">
            <h2>How it works</h2>
          </div>
          <div className="about-band__body">
            <p className="prose">
              Every SMILES string you submit goes through a fixed set of IUPAC nomenclature rules
              &mdash; there&rsquo;s no model and no training data involved, so the same input
              always produces the same output. Internally, the engine checks its own answer: it
              names the structure, then feeds that name into OPSIN, an independent
              name-to-structure parser, to see whether the round trip lands back on the same
              molecule. A name that round-trips cleanly under the engine&rsquo;s strict
              preferred-name rules is shown as a Preferred IUPAC Name (PIN). A name that
              round-trips but doesn&rsquo;t meet that strict standard is still shown, but labeled
              as a fallback rather than presented as equivalent to a PIN. When the engine
              isn&rsquo;t confident enough to produce a name at all, it abstains instead of
              guessing &mdash; and says so.
            </p>
          </div>
        </section>

        <section className="about-band about-band--split" aria-label="How each page works">
          <div className="about-band__head">
            <h2>How each page works</h2>
          </div>
          <div className="about-band__body">
            <div className="about-sub">
              <h3>Structure &rarr; IUPAC</h3>
              <p className="prose">
                Draw a molecule, then press Translate &mdash; the drawn structure is read straight
                out of the editor as a SMILES string and sent to the same engine behind the
                Translate page. The result lands in the same register entry you&rsquo;d see there:
                a double-ruled name means a confirmed Preferred IUPAC Name (PIN), a dashed
                underline is a lower-confidence but round-trip&ndash;verified fallback, a faint
                dotted underline means a name the engine could produce but not verify, and an
                empty ruled slot means it honestly couldn&rsquo;t name it at all.
              </p>
            </div>
            <div className="about-sub">
              <h3>IUPAC &rarr; Structure</h3>
              <p className="prose">
                This direction runs through OPSIN, not Orthonym&rsquo;s own naming engine in
                reverse. Orthonym&rsquo;s naming engine turns structures into names; going the other
                way needs a name-to-structure parser instead, so this page hands your text
                straight to OPSIN. If OPSIN can&rsquo;t resolve a name &mdash; a trade name, a
                misspelling, or anything outside strict IUPAC nomenclature &mdash; Orthonym says so
                plainly rather than guessing.
              </p>
            </div>
            <div className="about-sub">
              <h3>Explain and Learn</h3>
              <p className="prose">
                Every highlight comes from OPSIN&rsquo;s own parse of the name, never a guess. The
                name is broken into the parts OPSIN itself found &mdash; the parent skeleton, each
                substituent, the ending that names the main group, and prefixes that only move
                hydrogens around &mdash; and each part carries the atoms OPSIN built it from.
                Failure is per part: anything Orthonym can&rsquo;t pin to specific atoms is marked
                &ldquo;could not work out which atoms,&rdquo; and the parts around it are
                unaffected. Explain takes a typed SMILES or a typed name; Learn takes a drawn
                structure. Same breakdown, different way in.
              </p>
            </div>
          </div>
        </section>

        {/* At a glance — a bento mosaic of verified facts, not a card deck:
            same 1px seams, same 0px corners as every other grid on the site. */}
        <section className="about-band" aria-label="At a glance">
          <div className="about-band__title-row">
            <h2>At a glance</h2>
          </div>
          <ul className="about-cards">
            <li className="about-card">
              <span className="about-card__label">Engine</span>
              <p className="about-card__body">
                Deterministic and rule-based &mdash; not a language model.
              </p>
            </li>
            <li className="about-card">
              <span className="about-card__label">Version</span>
              <p className="about-card__body">
                Orthonym v1.0.0 &mdash; its first public release.
              </p>
            </li>
            <li className="about-card">
              <span className="about-card__label">License</span>
              <p className="about-card__body">MIT</p>
            </li>
            <li className="about-card">
              <span className="about-card__label">Author</span>
              <p className="about-card__body">Kohulan Rajan</p>
            </li>
          </ul>
          <div className="about-band__foot">
            <p className="prose-sm">
              Orthonym&rsquo;s naming engine is open source, released under the MIT License.{' '}
              <a
                className="about-link"
                href="https://github.com/Kohulan/Orthonym"
                target="_blank"
                rel="noopener noreferrer"
              >
                View the naming engine&rsquo;s source code
              </a>
              .
            </p>
          </div>
        </section>

        <section className="about-band" aria-label="Acknowledgments">
          <div className="about-band__title-row">
            <h2>Acknowledgments</h2>
          </div>
          <ul className="about-cards">
            <li className="about-card">
              <span className="about-card__label">IUPAC Blue Book 2013</span>
              <p className="about-card__body">
                Source of the nomenclature rules the naming engine implements.
              </p>
            </li>
            <li className="about-card">
              <span className="about-card__label">OPSIN</span>
              <p className="about-card__body">
                Used for name-to-structure conversion, to validate names.
              </p>
            </li>
            <li className="about-card">
              <span className="about-card__label">RDKit</span>
              <p className="about-card__body">Used for molecular perception.</p>
            </li>
            <li className="about-card">
              <span className="about-card__label">ChEBI</span>
              <p className="about-card__body">Source of a validation dataset.</p>
            </li>
          </ul>
        </section>
      </main>
    </>
  )
}

export default About
