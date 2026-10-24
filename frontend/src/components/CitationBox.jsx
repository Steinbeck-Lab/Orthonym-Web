import { Fragment, useState } from 'react'
import useCopy from '../lib/useCopy'
import { PAPER, SOFTWARE, bibtex, citationEntries, referenceAuthors } from '../lib/citation'
import useHealth from '../lib/useHealth'
import Icon from './Icon'

// A white About card. Left, the paper set as a printed reference and the
// exact engine to pin; right, the BibTeX, keys and values in two tones, with
// the surface's one primary button to copy it.
export default function CitationBox() {
  const health = useHealth()
  const engine = { version: health?.engine_version, commit: health?.engine_commit }
  const text = bibtex(engine)
  const entries = citationEntries(engine)
  const [copied, copyText] = useCopy(text, 1800)
  // Bumped on every copy, so the sweep restarts even on a second click
  // (a reused animation name would not replay).
  const [sweep, setSweep] = useState(0)

  async function copy() {
    if (await copyText()) setSweep((n) => n + 1)
  }

  return (
    <section className="cite card" id="cite" aria-labelledby="cite-title">
      <div className="cite__reference">
        <h2 className="about-section__title" id="cite-title">
          Cite Orthonym
        </h2>

        <figure className="cite__paper">
          <p className="cite__paper-title">{PAPER.title}</p>
          <figcaption className="cite__paper-meta">
            <span className="cite__authors">{referenceAuthors()}</span>
            <span className="cite__venue">
              <em>{PAPER.journal}</em> {PAPER.year}
            </span>
            <a className="cite__doi" href={PAPER.url} target="_blank" rel="noopener noreferrer">
              doi:{PAPER.doi}
            </a>
          </figcaption>
        </figure>

        <div className="cite__pin">
          <p className="cite__pin-lead">To pin the exact engine, cite the software too.</p>
          <dl className="cite__pin-list">
            <div>
              <dt>Version</dt>
              <dd>{engine.version ? `v${engine.version}` : '—'}</dd>
            </div>
            <div>
              <dt>Commit</dt>
              <dd>{engine.commit ? engine.commit.slice(0, 7) : '—'}</dd>
            </div>
            <div>
              <dt>Software DOI</dt>
              <dd>
                <a href={`https://doi.org/${SOFTWARE.doi}`} target="_blank" rel="noopener noreferrer">
                  {SOFTWARE.doi}
                </a>
              </dd>
            </div>
          </dl>
        </div>
      </div>

      <div className="cite__bib">
        <div className="cite__bib-head">
          <span className="cite__bib-label">BibTeX</span>
          <button type="button" className="btn btn--accent btn--sm cite__copy" onClick={copy}>
            <Icon name={copied ? 'check' : 'copy'} />
            {copied ? 'Copied' : 'Copy BibTeX'}
          </button>
          <span className="sr-only" role="status">
            {copied ? 'BibTeX copied to the clipboard' : ''}
          </span>
        </div>
        <pre className="cite__code" tabIndex={0} aria-label="BibTeX for the paper and the software">
          <code>
            {entries.map(({ type, key, fields }, e) => (
              <Fragment key={key}>
                {e > 0 && <span className="cite__line">{'\n'}</span>}
                <span className="cite__line">
                  <span className="cite__type">@{type}</span>
                  {'{'}
                  <span className="cite__key">{key}</span>,{'\n'}
                </span>
                {fields.map(([name, value], f) => (
                  <span className="cite__line" key={name}>
                    {'  '}
                    {name}
                    {' = {'}
                    <span className="cite__value">{value}</span>
                    {'}'}
                    {f < fields.length - 1 ? ',' : ''}
                    {'\n'}
                  </span>
                ))}
                <span className="cite__line">{'}\n'}</span>
              </Fragment>
            ))}
          </code>
          {sweep > 0 && <span className="cite__sweep" key={sweep} aria-hidden="true" />}
        </pre>
      </div>
    </section>
  )
}
