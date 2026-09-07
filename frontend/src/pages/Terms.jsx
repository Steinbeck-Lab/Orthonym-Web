import { Link } from 'react-router-dom'
import { LegalPage, LegalSection } from './LegalSection'
import './Legal.css'

// Terms of Use, followed by Orthonym's own licence and the third-party
// attributions for the components whose licences require a notice (CDK and
// centres, both copyleft) or which it is simply honest to cite.
//
// Structure and the eight numbered conditions follow the reference
// implementation (Beilstein-Institut/BChemXtractWeb,
// frontend/src/pages/TermsPage.tsx), retargeted at what Orthonym actually is
// and at the entity that operates it. Clause 3 is the one that changed most:
// the reference disclaims "string representations (InChI, SMILES, molecular
// formulas, RInChI)", and the equivalent claim here has to be made carefully,
// because Orthonym's whole product is that it TELLS you how much confidence it
// can claim for a name. Saying "may contain errors" flatly would understate
// the product; saying nothing would overstate it. The clause therefore says
// both: the tier is honest, and an honest tier is still not a warranty.
//
// The licence text below is the repository's own /LICENSE, reproduced
// verbatim from the file rather than retyped. Owner decision this session:
// Orthonym is MIT, © 2026 Kohulan Rajan, matching the vendored Orthonym
// snapshot exactly (backend/vendor/orthonym/LICENSE) — the repo had no
// LICENSE file at all before this page needed one, and /LICENSE was created
// from that same text so the two can never disagree.
//
// The third-party list is deliberately NOT the full dependency manifest.
// Every entry below is either copyleft (so a notice is owed), a vendored
// binary this repository actually redistributes, or the engine the product
// is a showcase for. Everything else is a link to the manifest, as the
// reference does. Provenance for the three jars is
// backend/vendor/orthonym/NOTICE and backend/vendor/cdk/NOTICE, both of
// which are considerably more careful than this page can be, so this page
// cites them rather than paraphrasing them.

const MIT_LICENSE_TEXT = `MIT License

Copyright (c) 2026 Kohulan Rajan

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.`

// Ordered by how load-bearing each one is to a name appearing on screen,
// not alphabetically: engine, verifier, stereo labeller, renderer, then the
// frameworks that carry them.
const THIRD_PARTY = [
  {
    // NO href, deliberately. github.com/Kohulan/Orthonym is a PRIVATE
    // repository — checked unauthenticated, it answers 404 — so linking it
    // would hand every visitor a dead link that looks like a broken site.
    // Give it an href again the day the repository is published.
    name: 'Orthonym 1.0.0',
    spdx: 'MIT',
    note: 'The rule-based SMILES-to-IUPAC naming engine this site exists to show. Vendored as a source snapshot under backend/vendor/orthonym and installed at image build time. © 2026 Kohulan Rajan. Its repository is not public.',
  },
  {
    name: 'OPSIN 2.9.0',
    href: 'https://github.com/dan2097/opsin',
    spdx: 'MIT',
    note: 'Parses a name back into a structure. It is what makes the round-trip verdict under every name possible, and it is also the whole of /from-name. Shipped as an unmodified executable jar and invoked as a separate program. © Daniel Lowe and contributors.',
  },
  {
    name: 'centres 1.5',
    href: 'https://github.com/SiMolecule/centres',
    spdx: 'LGPL-3.0',
    note: 'Assigns Cahn-Ingold-Prelog stereo descriptors. Shipped as an unmodified fat jar that itself redistributes CDK and javax.vecmath; see the notice below. Upstream states BSD-2-Clause in its LICENSE file and LGPL-3.0 in its pom, so the jar is treated here as carrying the more restrictive of the two.',
  },
  {
    name: 'Chemistry Development Kit 2.12',
    href: 'https://github.com/cdk/cdk',
    spdx: 'LGPL-2.1-or-later',
    note: 'Draws every structure on the site and annotates the CIP descriptors onto the drawing; also a second opinion on any SMILES RDKit refuses. Shipped unmodified and loaded at runtime in its own classloader, not linked.',
  },
  {
    name: 'RDKit',
    href: 'https://www.rdkit.org/',
    spdx: 'BSD-3-Clause',
    note: 'Reads and canonicalises structures, computes formulae, and is the depiction fallback for any process without a JVM. Installed from PyPI, not redistributed by this repository.',
  },
  {
    name: 'Ketcher 2.6.2',
    href: 'https://github.com/epam/ketcher',
    spdx: 'Apache-2.0',
    note: 'The structure editor on /explain. Bundled and served from this origin, running its Indigo engine entirely in your browser — it contacts no chemistry server. © EPAM Systems.',
  },
  {
    name: 'FastAPI',
    href: 'https://fastapi.tiangolo.com/',
    spdx: 'MIT',
    note: 'The Python web framework answering every request.',
  },
  {
    name: 'Celery',
    href: 'https://docs.celeryq.dev/',
    spdx: 'BSD-3-Clause',
    note: 'Runs the naming workers. Every name is computed in a worker process, never in the web process.',
  },
  {
    name: 'Redis 7.4',
    href: 'https://redis.io/',
    spdx: 'RSALv2 / SSPLv1',
    note: 'The message broker, job store, shared name cache and rate-limit counters, all at once. Run as a server alongside the application; not redistributed and not linked, so its terms do not reach this software.',
  },
  {
    name: 'JPype',
    href: 'https://jpype.readthedocs.io/',
    spdx: 'Apache-2.0',
    note: 'The Python-to-JVM bridge that lets a worker hold a live OPSIN rather than starting a subprocess per name.',
  },
  {
    name: 'React',
    href: 'https://react.dev/',
    spdx: 'MIT',
    note: 'The frontend framework, with React Router for the routes.',
  },
  {
    name: 'Saira Condensed, Public Sans, JetBrains Mono',
    href: 'https://openfontlicense.org/',
    spdx: 'OFL-1.1',
    note: 'The three typefaces, self-hosted from this origin. No font is fetched from Google Fonts or any other third party.',
  },
]

// Each condition is one node so a clause can carry a link without the list
// being split into "plain" and "rich" halves. Each carries its own `id`
// rather than being keyed by array index: reordering a clause with an index
// key makes React reuse the wrong DOM node, and these WILL be reordered --
// legal text is edited by insertion.
const CONDITIONS = [
  {
    id: 'licence',
    body: (
      <>
        Orthonym is released under the MIT License, reproduced below, and so is the Orthonym engine
        behind it. Bundled third-party components keep their own licences, as set out in the
        sections that follow.
      </>
    ),
  },
  {
    id: 'free-use',
    body: (
      <>
        Everybody is free to use Orthonym to translate chemical structures into IUPAC names, and to use
        the names it produces.
      </>
    ),
  },
  {
    id: 'as-is',
    body: (
      <>
        This site and its content are provided for use “as is”. No representation or warranty is made
        with respect to the site or its contents, including as to quality, completeness, timeliness or
        accuracy. Names, structures, molecular formulae and depictions are generated automatically.
        Orthonym states, for every name, how far it was able to verify that name — a verified name, a
        fallback, a best-effort attempt or an abstention — and that statement is made honestly and is
        the point of the site. It is not a warranty that the name is correct. In particular, no
        result from this site should be relied upon as the sole basis for a regulatory, safety,
        clinical, purchasing or publication decision without independent checking.
      </>
    ),
  },
  {
    id: 'privacy',
    body: (
      <>
        The <Link to="/privacy">Privacy Policy</Link> applies to your use of this site.
      </>
    ),
  },
  {
    id: 'changes',
    body: (
      <>
        The operator reserves the right, in whole or in part, to change or delete this site, to suspend
        your access, or to terminate the site at any time and without notice. This is a free
        research service; no availability, uptime or response time is promised. These terms may be
        revised, and the version in force is the one published here.
      </>
    ),
  },
  {
    // The rate limiter has been enforcing this since long before the page
    // said it: backend/app/core/config.py sets 2 concurrent jobs, 20
    // jobs/hour, 60 naming requests/minute, 300 polls/minute and 10
    // downloads/minute, all per IP address, all answered with a 429. A
    // service should publish the rule it already denies people on.
    id: 'acceptable-use',
    body: (
      <>
        Use of the site is subject to per-IP request limits, which the service enforces
        automatically and answers with an HTTP 429 response. Circumventing or attempting to
        circumvent those limits is not permitted, and access may be withdrawn for conduct that
        degrades the service for other users.
      </>
    ),
  },
  {
    // The Privacy Policy discloses that a submitted structure is
    // standardised, hashed and kept in a shared cache for seven days, where
    // it answers other people's requests too. The Terms authorised none of
    // that, and said nothing about who owns what.
    id: 'your-content',
    body: (
      <>
        You keep whatever rights you have in the structures you submit. The operator claims none,
        and takes only the permission needed to process a submission, return a result, and keep it
        in the shared cache described in the <Link to="/privacy">Privacy Policy</Link>. No rights
        are claimed in the names the site returns, and no restriction is placed on your use of
        them.
      </>
    ),
  },
  {
    id: 'liability',
    body: (
      <>
        Except as stated in the next sentence, the operator is not liable for damages of any nature
        resulting directly or indirectly from the use or non-use of the information provided on this
        site, unless the damage was caused deliberately or by gross negligence on the part of the
        operator. Liability for injury to life, body or health, and any other liability that cannot
        be excluded by agreement — in particular under the Produkthaftungsgesetz — is unaffected.
      </>
    ),
  },
  {
    id: 'third-party-sites',
    body: (
      <>
        The operator is not liable for the content of any third-party site this site links to.
      </>
    ),
  },
  {
    id: 'law',
    body: (
      <>
        These terms are governed by the law of the Federal Republic of Germany. Where the user is a
        merchant, a legal person under public law or a public-law special fund, the sole place of
        jurisdiction for all disputes arising out of or in connection with the use of this site is
        Jena; nothing here removes the protection a consumer has under the mandatory law of their
        own place of residence. Should any provision of these terms be or become invalid, the
        remainder stays in force.
      </>
    ),
  },
]

function Terms() {
  return (
    <LegalPage
      title="Terms of Use"
      lede="What you may do with Orthonym, what it promises, and what it does not."
      label="Terms of Use"
    >
        <LegalSection
          id="terms-conditions"
          index="Conditions"
          title="Terms and conditions of use"
          note={
            <>
              This site and its content are protected by copyright law. Use of the site is subject
              to these terms. “The operator” below means the Cheminformatics and Computational
              Metabolomics group at Friedrich-Schiller-Universität Jena, identified in full on the{' '}
              <Link to="/imprint">Impressum</Link>.
            </>
          }
        >
            <ol>
              {CONDITIONS.map(({ id, body }) => (
                <li key={id}>{body}</li>
              ))}
            </ol>
        </LegalSection>

        <section className="card legal-section" aria-labelledby="terms-licence">
          <div className="legal-section__head">
            <p className="legal-section__index">MIT</p>
            <h2 className="legal-section__title" id="terms-licence">
              Orthonym — MIT License
            </h2>
            <p className="legal-section__note">
              Reproduced verbatim from the <code>LICENSE</code> file at the root of Orthonym’s source
              tree.
            </p>
          </div>

          <pre className="legal-license">{MIT_LICENSE_TEXT}</pre>
        </section>

        <section className="card legal-section" aria-labelledby="terms-third-party">
          <div className="legal-section__head">
            <p className="legal-section__index">Attribution</p>
            <h2 className="legal-section__title" id="terms-third-party">
              Third-party components
            </h2>
            <p className="legal-section__note">
              The load-bearing dependencies and their licences: everything that carries a copyleft
              notice, every binary this build redistributes, and the engine the site exists to
              show. It is not the complete dependency manifest.
            </p>
          </div>

          {/* role="list" is not redundant here: WebKit removes the implicit
              list/listitem roles from a <ul> whose computed list-style is
              `none`, and `.legal-parties` sets exactly that. Without it
              VoiceOver stops announcing "list, 12 items" and stops giving
              item position on the licence inventory. A no-op in Chromium. */}
          <ul className="legal-parties" role="list">
            {THIRD_PARTY.map((entry) => (
              <li className="legal-party" key={entry.name}>
                <p className="legal-party__head">
                  {/* An entry with no `href` renders as plain text rather than
                      as a link to nowhere. Orthonym is the one such entry
                      today: its repository is private and answers 404 to an
                      anonymous visitor. */}
                  {entry.href ? (
                    <a
                      className="legal-party__name"
                      href={entry.href}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      {entry.name}
                    </a>
                  ) : (
                    <span className="legal-party__name">{entry.name}</span>
                  )}
                  {/* NOT aria-label. A bare <span> maps to role=generic and
                      aria-label is prohibited on it by ARIA 1.2 — Chrome
                      honours it, Firefox and Safari drop it, so the
                      disambiguating "Licence:" never reached two of three
                      engines. An `.sr-only` prefix is announced everywhere.
                      The string is written as an expression, not as text with
                      a trailing space, because a reformat that wraps the line
                      would silently eat the space. */}
                  <span className="legal-party__spdx">
                    <span className="sr-only">{'Licence: '}</span>
                    {entry.spdx}
                  </span>
                </p>
                <p className="legal-party__note">{entry.note}</p>
              </li>
            ))}
          </ul>
        </section>

        <LegalSection id="terms-copyleft" index="LGPL" title="Copyleft notice for the bundled jars">
            <p>
              Orthonym ships three Java archives unmodified and runs each of them as a separate
              program: OPSIN, which verifies a name by parsing it back; centres, which assigns CIP
              stereo descriptors; and CDK, which draws every structure on the site. Orthonym does not
              link against, embed or modify any of them.
            </p>
            <p>
              Two of the three carry copyleft terms that travel with the binary. CDK is distributed
              under the GNU Lesser General Public License, version 2.1 or later. The centres jar is
              a shaded archive that itself redistributes CDK, <code>javax.vecmath</code> (GPLv2 with
              the Classpath exception) and Beam. Both licences permit unmodified redistribution and
              use as a separately invoked program, and both carry a source-availability obligation,
              which the upstream projects satisfy:{' '}
              <a href="https://github.com/cdk/cdk" target="_blank" rel="noopener noreferrer">
                CDK
              </a>
              ,{' '}
              <a
                href="https://github.com/SiMolecule/centres"
                target="_blank"
                rel="noopener noreferrer"
              >
                centres
              </a>{' '}
              and{' '}
              <a
                href="https://github.com/hharrison/vecmath"
                target="_blank"
                rel="noopener noreferrer"
              >
                vecmath
              </a>
              .
            </p>
            <p>
              The full provenance of every vendored artefact — version, SHA-256, how it is invoked,
              and which of its bundled components carry which terms — is recorded alongside the
              artefacts themselves, in <code>backend/vendor/cdk/NOTICE</code> and{' '}
              <code>backend/vendor/orthonym/NOTICE</code>. Ask the operator for a copy of either
              if you need it; those files, not this page, are the authoritative record.
            </p>
            <h3>Citing Orthonym</h3>
            <p>
              If this site helped with work you publish, please cite the naming engine and the
              site: <em>Orthonym v1.0.0</em> (Kohulan Rajan) for the names themselves, and Orthonym
              for the interface that produced them. Names verified by round-trip were checked with{' '}
              <a href="https://github.com/dan2097/opsin" target="_blank" rel="noopener noreferrer">
                OPSIN 2.9.0
              </a>
              , which is worth citing alongside if the verification matters to your argument.
            </p>
            <p className="legal-updated">Version 1 — 6 September 2026</p>
        </LegalSection>
    </LegalPage>
  )
}

export default Terms
