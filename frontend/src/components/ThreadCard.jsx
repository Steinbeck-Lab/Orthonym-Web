/**
 * One entry in the credits list — a materials card for one dependency.
 *
 * Each card says what Orthonym is built on: the project, a short code for it,
 * and where it is used. The credits go here rather than into a paragraph of
 * prose, so a reader scanning for "what is this built on" finds each answer
 * in a list they can scan.
 *
 * TWO KINDS OF SWATCH, and the difference is disclosed rather than papered
 * over. RDKit, ChEBI and the Beilstein-Institut publish real marks and those
 * are used as-is, unaltered and unrecoloured, which is the only honest way to
 * show someone else's trademark. IUPAC's site refuses scripted downloads and
 * OPSIN — a Java library, not a product — has never had a logo at all, so
 * those two get a typographic lockup in the page's own face. A drawn
 * substitute presented as though it were the real mark would be a small lie
 * about someone else's identity.
 */
export default function ThreadCard({ code, name, role, logo, alt, href }) {
  const swatch = logo ? (
    <img className="thread__logo" src={logo} alt={alt} loading="lazy" />
  ) : (
    // Not a fake logo: a wordmark set in the page's own type, which reads as
    // this page's typography rather than as that project's identity.
    <span className="thread__lockup" aria-hidden="true">
      {name}
    </span>
  )

  return (
    <li className="thread">
      <span className="thread__code">{code}</span>
      <span className="thread__swatch">{swatch}</span>
      <span className="thread__name">
        {href ? (
          <a href={href} target="_blank" rel="noopener noreferrer">
            {name}
          </a>
        ) : (
          name
        )}
      </span>
      <span className="thread__role">{role}</span>
    </li>
  )
}
