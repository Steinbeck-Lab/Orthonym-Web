// The section card the three legal routes are built out of, and the page
// shell that holds them.
//
// It lived inside Privacy.jsx first, where it was used seven times, while
// Imprint.jsx and Terms.jsx hand-wrote the identical markup inline eight
// times between them. Hoisting it here removed 36 lines and, more usefully,
// the possibility of the three pages drifting apart — which is the same
// reason all three already share one stylesheet rather than three.
//
// Two sections deliberately do NOT use `LegalSection`: the Impressum's
// operator block and the Terms' third-party list, because their bodies are a
// `<dl>` and a `<ul>` rather than prose and so must not be wrapped in
// `.prose legal-prose`. They stay inline, one line each.

// The route opening. Not a card: a titled white card here would stack a
// second white rectangle under the white header notch, which is the exact
// bug `.page-head` was deleted for on 2026-09-02 (DESIGN.md). The
// `page-hero--legal` modifier narrows it to the same 1100px the cards take;
// without it the band overhangs them by ~280px.
export function LegalPage({ title, lede, label, children }) {
  return (
    <>
      <section className="page-hero page-hero--legal" aria-label="Introduction">
        <h1 className="page-hero__title">{title}</h1>
        <p className="page-hero__lede">{lede}</p>
      </section>

      <main className="legal" aria-label={label}>
        {children}
      </main>
    </>
  )
}

export function LegalSection({ id, index, title, note, children }) {
  return (
    <section className="card legal-section" aria-labelledby={id}>
      <div className="legal-section__head">
        <p className="legal-section__index">{index}</p>
        <h2 className="legal-section__title" id={id}>
          {title}
        </h2>
        {note ? <p className="legal-section__note">{note}</p> : null}
      </div>
      <div className="prose legal-prose">{children}</div>
    </section>
  )
}
