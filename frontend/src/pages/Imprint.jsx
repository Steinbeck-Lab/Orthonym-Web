import { Fragment } from 'react'
import { Link } from 'react-router-dom'
import { LegalPage, LegalSection } from './LegalSection'
import './Legal.css'

// Imprint — the legal identification of the site's operator, required of
// every German-hosted commercial or quasi-commercial web offering.
//
// The route is /imprint; the visible label is the German "Impressum",
// because that is the legally recognised term and the word a German visitor
// looks for. Same split the reference implementation uses
// (Beilstein-Institut/BChemXtractWeb, frontend/src/pages/ImprintPage.tsx).
//
// WHOSE Impressum this is, and why: Orthonym (this web app) is a showcase for
// the Orthonym engine and is to be hosted by the Steinbeck Lab, so the
// operator named here is the Cheminformatics and Computational Metabolomics
// group at Friedrich-Schiller-Universität Jena — the same entity, in the
// same shape, that the group's own DECIMER.ai names in
// resources/views/impressum.blade.php. Every fact below is taken from that
// file rather than composed here, so the two sites cannot drift apart:
//
//   Friedrich-Schiller-Universität Jena
//   Institut für Anorganische und Analytische Chemie
//   Arbeitsgruppe: Cheminformatics and Computational Metabolomics
//   Lessingstr. 8, 07743 Jena
//   Ansprechpartner: Prof. Dr. Christoph Steinbeck
//   Telefon: +49 3641 948181 · christoph.steinbeck@uni-jena.de
//   https://cheminf.uni-jena.de/
//
// Owner decision (asked and answered this session): name the WORKING GROUP,
// as DECIMER.ai does, rather than the university as a body corporate
// represented by its President. A stricter reading of the statute would name
// the university; the two sites reading the same way was worth more.
//
// One deliberate departure from DECIMER.ai's wording: it cites "Abschnitt 5
// TMG". The Telemediengesetz was superseded by the Digitale-Dienste-Gesetz
// on 14 May 2024 and the identification duty now lives in § 5 DDG. The old
// citation is named alongside the new one rather than silently dropped,
// because a reader comparing the two sites should be able to see that this
// is the same obligation and not a different one.
//
// Note there is no Beilstein-Institut mark on this page, unlike the
// reference. The institute is credited in the footer as a rights holder of
// its own artwork; it does not operate this site, and putting its wordmark
// on an Impressum would say that it does.

// Label/value rows, in the order the source document lists them. `value` is
// a node rather than a string because three of them carry a link or a line
// break, and splitting the list into "plain" and "rich" halves would only
// mean maintaining the order twice.
const DETAILS = [
  {
    label: 'Institution',
    value: (
      <>
        Friedrich-Schiller-Universität Jena
        <br />
        Institut für Anorganische und Analytische Chemie
      </>
    ),
  },
  {
    label: 'Address',
    value: (
      <>
        Lessingstr. 8
        <br />
        07743 Jena
        <br />
        Germany
      </>
    ),
  },
  // "Contact", NOT "Represented by". The statutory representative of a
  // Körperschaft des öffentlichen Rechts is its President (Prof. Dr. Andreas
  // Marx, uni-jena.de/impressum), which is what the Privacy page says two
  // clicks away — and the VAT ID and supervisory-authority rows below are the
  // university's for the same reason. Prof. Steinbeck is the Ansprechpartner
  // DECIMER.ai names, and that is the word for it.
  { label: 'Contact', value: 'Prof. Dr. Christoph Steinbeck' },
  // NOT DECIMER.ai's "+49 3641 948181". That extension (48181) does not
  // appear anywhere in the institute's official staff directory, which lists
  // Prof. Steinbeck at +49 3641 9-48780 and gives 9-48171 to the group's team
  // assistant. The directory is the primary source and DECIMER's number could
  // not be attributed to any person or unit, so the directory number is used
  // here. Flagged to the owner: if 948181 is a real group line, say so and
  // this goes back.
  { label: 'Phone', value: '+49 3641 9-48780' },
  {
    label: 'Email',
    value: (
      <a href="mailto:christoph.steinbeck@uni-jena.de">christoph.steinbeck@uni-jena.de</a>
    ),
  },
  {
    label: 'Website',
    value: (
      <a href="https://cheminf.uni-jena.de/" target="_blank" rel="noopener noreferrer">
        cheminf.uni-jena.de
      </a>
    ),
  },
  // Both are missing from DECIMER.ai's Impressum; only the first is actually
  // required. § 5 (1) Nr. 6 DDG requires the § 27a UStG number where one
  // exists, and the university has one. § 5 (1) Nr. 3 DDG requires naming a
  // supervisory authority only for a service offered within an activity that
  // needs official authorisation, which a university research tool is not —
  // the row is carried anyway because the university's own Impressum carries
  // it and a reader checking one against the other should find it. Note it is
  // the STATE supervisor of the university, a different body from the
  // data-protection supervisor, which belongs on the Privacy page. Both are
  // quoted from uni-jena.de/impressum.
  { label: 'VAT ID', value: 'DE 150546536 (§ 27a UStG, Friedrich-Schiller-Universität Jena)' },
  {
    label: 'Supervisory authority',
    value: (
      <>
        Thüringer Ministerium für Bildung, Wissenschaft und Kultur
        <br />
        Werner-Seelenbinder-Straße 7
        <br />
        99096 Erfurt
      </>
    ),
  },
]

function Imprint() {
  return (
    <LegalPage
      title="Impressum"
      lede="Who operates this site, and who is answerable for what it says."
      label="Impressum"
    >
        <section className="card legal-section" aria-labelledby="imprint-operator">
          <div className="legal-section__head">
            <p className="legal-section__index">§ 5 DDG (formerly § 5 TMG)</p>
            <h2 className="legal-section__title" id="imprint-operator">
              Information required by law
            </h2>
          </div>

          <h3 className="legal-entity__name">Cheminformatics and Computational Metabolomics</h3>
          <p className="legal-entity__kind">
            A research group of Friedrich-Schiller-Universität Jena, a corporation under German
            public law.
          </p>

          <dl className="legal-facts">
            {/* A keyed Fragment, not a wrapper <div>: the dt/dd pair has to
                land directly on `.legal-facts`'s own grid, and a real element
                would need `display: contents` to get back out of the way. */}
            {DETAILS.map(({ label, value }) => (
              <Fragment key={label}>
                <dt>{label}</dt>
                <dd>{value}</dd>
              </Fragment>
            ))}
          </dl>
        </section>

        <LegalSection id="imprint-liability" index="Disclaimer" title="Liability for content and links">
            <p>
              The content of these pages was created with all due care. We cannot, however,
              guarantee that it is current, reliable or complete. Under the general law we are
              responsible for our own content on these pages. We are not responsible for
              information provided or collected by third parties, we do not monitor the
              information that passes through this service, and we do not search it for signs of
              unlawful activity. Where we become aware of a specific infringement we will block
              or remove the content concerned, as § 7 DDG in conjunction with Articles 4 to 8 of
              Regulation (EU) 2022/2065 and § 8 DDG require.
            </p>
            <p>
              Responsibility for the content of an external site reached from a link on this site
              lies solely with the operator of that site. No unlawful content was apparent on any
              linked page at the time the link was added. We will remove a link as soon as an
              infringement becomes known to us.
            </p>
        </LegalSection>

        <LegalSection id="imprint-names" index="Accuracy" title="About the names this site produces">
            <p>
              Orthonym generates IUPAC names automatically, by rule, from the structure you give it.
              Every name is shown with the confidence Orthonym is able to claim for it, and a name
              that could not be verified is labelled as such rather than presented as if it had
              been. That labelling is the point of the site and it is not decoration.
            </p>
            <p>
              A verified name is still a machine-generated name. Nothing here is a warranty that a
              name, a structure, a formula or a depiction is correct or fit for any particular
              purpose, and no result should be relied upon for a regulatory, safety or publication
              decision without independent checking. The terms that govern your use of the site
              are set out in the <Link to="/terms">Terms of Use</Link>, and what the site does with
              your data in the <Link to="/privacy">Privacy Policy</Link>.
            </p>
        </LegalSection>

        <LegalSection id="imprint-copyright" index="Copyright" title="Copyright">
            {/* This clause used to require written consent for reproducing
                "these pages and their content — text, images, graphics and
                design", which is precisely what the MIT licence on the Terms
                page grants outright. Two shipped documents cannot say opposite
                things about the same files. The consent requirement now covers
                only what MIT does not reach: artwork owned by someone else. */}
            <p>
              The software that produces these pages — their markup, their stylesheets and their
              design — is released under the MIT License, which grants reproduction, adaptation and
              redistribution without anyone's permission. The licence text and the third-party
              components it depends on are on the <Link to="/terms">Terms of Use</Link>.
            </p>
            <p>
              What that licence does not cover is artwork this site displays under someone else's
              rights: the Beilstein-Institut wordmark in the footer, and any other third-party logo
              or mark. Those remain with their owners, are subject to German copyright and
              trade-mark law, and use beyond the limits of that law needs their written consent.
            </p>
            <p className="legal-updated">Version 1 — 6 September 2026</p>
        </LegalSection>
    </LegalPage>
  )
}

export default Imprint
