import { bibtex, ris } from '../lib/citation'
import useHealth from '../lib/useHealth'
import CopyButton from './CopyButton'

// The paper first, then the software at the version this deployment runs.
// Until /api/health answers, the software entry simply has no version.
export default function CitationBox() {
  const health = useHealth()
  const engine = { version: health?.engine_version, commit: health?.engine_commit }
  const formats = [
    ['BibTeX', bibtex(engine)],
    ['RIS', ris(engine)],
  ]

  return (
    <section className="cite card" id="cite" aria-labelledby="cite-title">
      <div className="about-section__head">
        <h2 className="about-section__title" id="cite-title">
          Cite Orthonym
        </h2>
        <p className="about-section__note">
          Please cite the paper. To pin the exact engine, cite the software too.
        </p>
      </div>
      <div className="cite__formats">
        {formats.map(([label, text]) => (
          <div className="cite__format" key={label}>
            <div className="cite__head">
              <h3 className="cite__label">{label}</h3>
              <CopyButton text={text} label={`Copy ${label}`} />
            </div>
            <pre className="about-code" tabIndex={0} aria-label={`${label} citation`}>
              {text}
            </pre>
          </div>
        ))}
      </div>
    </section>
  )
}
