// The empty state of the results panel. Instead of a vast white void with a
// single "nothing here yet" line, it teaches the one thing a newcomer most
// needs: what the five confidence marks mean. The marks shown here are the
// exact rule styles a real result carries (double / dashed / dotted / faint
// / struck), so the legend and the results speak the same language.
//
// Confidence is monochrome on purpose — it is the product's core signal and
// must never be a colour, so the crimson accent never appears here.

const TIERS = [
  {
    key: 'pin',
    name: 'Preferred IUPAC Name',
    code: 'PIN',
    body: 'Verified. OPSIN parses the name back to your exact structure, and it meets the strict preferred-name rules.',
  },
  {
    key: 'fallback',
    name: 'Verified fallback',
    code: 'FALLBACK',
    body: 'Round-trips correctly, but is a valid systematic name rather than the single preferred one.',
  },
  {
    key: 'best-effort',
    name: 'Best effort',
    code: 'UNVERIFIED',
    body: 'A real name OPSIN could not confirm. Shown only with best-effort mode on, and never as a PIN.',
  },
  {
    key: 'abstain',
    name: 'Honest abstain',
    code: 'NO NAME',
    body: 'No confident name. The engine refuses rather than guess.',
  },
  {
    key: 'error',
    name: 'Parse error',
    code: 'BAD INPUT',
    body: 'The SMILES string could not be read.',
  },
]

export default function ConfidenceLegend() {
  return (
    <section className="home-legend" aria-label="What the confidence marks mean">
      <p className="home-legend__title">What the mark under each name means</p>
      <ul className="home-legend__list">
        {TIERS.map((tier) => (
          <li className="home-legend__row" key={tier.key}>
            <span className={`home-legend__mark home-legend__mark--${tier.key}`} aria-hidden="true" />
            <div className="home-legend__text">
              <span className="home-legend__name">
                {tier.name} <span className="home-legend__code">{tier.code}</span>
              </span>
              <span className="home-legend__body">{tier.body}</span>
            </div>
          </li>
        ))}
      </ul>
      <p className="home-legend__foot">
        Submit a SMILES string on the left and each result appears here, carrying its own mark.
      </p>
    </section>
  )
}
