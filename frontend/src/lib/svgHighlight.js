import DOMPurify from 'dompurify'

// Shared by every page that draws an RDKit-generated SVG and highlights
// atoms/bonds on hover (Explain.jsx). `sanitizeSvg` carries the
// DOMPurify configuration, and two independent copies of a sanitizer config
// is exactly the kind of thing that drifts silently -- one copy gets a fix,
// the other doesn't, and the one that didn't is an XSS hole. It lives here,
// in exactly one place, for that reason. Do not re-duplicate any of this
// into a future page; import it instead.

// The SVG comes from Orthonym's own backend (RDKit-generated structure
// drawing, never raw user text echoed into markup), but it's injected
// directly into the DOM (see the callers' effects) -- unlike an <img
// src="data:..."> elsewhere in this app, inlined SVG becomes live DOM and
// could execute embedded scripts/handlers if the backend or a future
// change ever introduced one. Sanitize defensively regardless of the
// current trusted source. `class`/`style` are explicitly kept: the
// hover-highlighting mechanism depends on both (atom-N/bond-N classes to
// find elements, inline style to read/restore their original stroke and
// fill colors).
export function sanitizeSvg(svg) {
  return DOMPurify.sanitize(svg, {
    USE_PROFILES: { svg: true, svgFilters: true },
    ADD_ATTR: ['class', 'style'],
  })
}

// Matches a CSS class attribute like "bond-1 atom-1 atom-2" or "atom-2" --
// pulls out every atom-N reference on that SVG element.
export const ATOM_REF_RE = /atom-(\d+)/g

export function atomRefsOf(classAttr) {
  if (!classAttr) return []
  return [...classAttr.matchAll(ATOM_REF_RE)].map((m) => Number(m[1]))
}
