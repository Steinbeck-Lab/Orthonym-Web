import './About.css'

// About Orthonym: what it is, how it works, its measured accuracy, and the
// verified facts (author, license, acknowledgments) behind the naming
// engine it showcases. Every claim here traces to the engine's own repo
// (pyproject.toml, LICENSE, README) or to this app's own shipped copy
// (Home.jsx's disclaimer) — nothing invented.
function About() {
  return (
    <section className="about-page page-shell" aria-label="About">
      <h1 className="about-page__title">About Orthonym</h1>

      <p className="about-page__lead">
        Orthonym is a public showcase for a
        deterministic, rule-based SMILES-to-IUPAC-name engine &mdash; built so visitors can try
        it on real molecules and see exactly how it behaves, including where it succeeds, where
        it falls back, and where it honestly declines to guess.
      </p>

      <section className="about-block" aria-label="How it works">
        <h2 className="about-block__heading">How it works</h2>
        <p className="about-block__body">
          Every SMILES string you submit goes through a fixed set of IUPAC nomenclature rules
          &mdash; there&rsquo;s no model and no training data involved, so the same input always
          produces the same output. Internally, the engine checks its own answer: it names the
          structure, then feeds that name into OPSIN, an independent name-to-structure parser,
          to see whether the round trip lands back on the same molecule. A name that round-trips
          cleanly under the engine&rsquo;s strict preferred-name rules is shown as a Preferred
          IUPAC Name (PIN). A name that round-trips but doesn&rsquo;t meet that strict standard is
          still shown, but labeled as a fallback rather than presented as equivalent to a PIN.
          When the engine isn&rsquo;t confident enough to produce a name at all, it abstains
          instead of guessing &mdash; and says so.
        </p>
      </section>

      <section className="about-block" aria-label="How accurate is it">
        <h2 className="about-block__heading">How accurate is it?</h2>
        <div className="about-accuracy">
          <p className="about-accuracy__lead">
            Orthonym&rsquo;s naming engine is alpha-stage and rule-based &mdash; the same input
            always gives the same output, and it will tell you when it isn&rsquo;t sure.
          </p>
          <p className="about-accuracy__body">
            Measured round-trip accuracy: <strong>~30.4% overall</strong> (ChEBI 29.6%, PubChem
            16.9%), rising to <strong>~92.2%</strong> on its own OPSIN self-test corpus. A
            lower-confidence name is always shown as such, never hidden; when it can&rsquo;t
            confidently name a molecule, it abstains instead of guessing.
          </p>
        </div>
      </section>

      <section className="about-block" aria-label="At a glance">
        <h2 className="about-block__heading">At a glance</h2>
        <ul className="about-cards">
          <li className="about-card">
            <span className="about-card__label">Engine</span>
            <p className="about-card__body">
              Deterministic and rule-based &mdash; not a language model.
            </p>
          </li>
          <li className="about-card">
            <span className="about-card__label">Stage</span>
            <p className="about-card__body">
              Alpha. Rules and coverage are still being built out.
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
        <p className="about-block__body">
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
      </section>

      <section className="about-block" aria-label="Acknowledgments">
        <h2 className="about-block__heading">Acknowledgments</h2>
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
    </section>
  )
}

export default About
