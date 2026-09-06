/**
 * One entry in the thread list — a pattern chart's materials card.
 *
 * Every embroidery pattern ships a floss list: which threads the piece is
 * worked in, their maker's code, and where each one is used. That is exactly
 * the shape of Orthonym's dependency credits, so the credits go here rather than
 * into a paragraph of prose: a reader scanning for "what is this built on"
 * finds it in the place the world has already taught them to look.
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
