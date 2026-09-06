/**
 * The × joining the two institutions, painted with a loaded, drying brush.
 *
 * Modelled on a reference the owner supplied, whose whole character is DRY
 * BRUSH: a confident loaded head, then the stroke breaking into separate
 * bristle streaks as the paint runs out, with the tail splitting into
 * fibres rather than tapering cleanly. That texture is the thing being asked
 * for -- a smooth tapered sliver reads as a swoosh, not as paint.
 *
 * Nothing here traces the reference: it is a stock image, watermarked, and not
 * ours to ship. This is an original mark built to the same physics.
 *
 * HOW IT IS BUILT. A brush is not one shape, it is a bundle of bristles that
 * start together and separate as they dry, so that is literally the model:
 *   - a BODY, the wet head of the stroke, a filled outline with a ragged edge
 *   - BRISTLES, thin slivers at their own offsets across the brush's width,
 *     each starting where the body thins and running past its end
 *   - FLECKS, a few detached marks thrown past the tail
 * `stroke-width` could not do any of this -- it is constant along a path -- so
 * every part is a closed filled outline generated from a centreline.
 *
 * Every value is deterministic. `hash()` is the standard sine-fract hash, not
 * Math.random: a painted mark should be THIS painted mark on every render, and
 * a random one would also differ between a server render and its hydration.
 */

const SAMPLES = 40

// Deterministic pseudo-noise in [0,1). Same input, same output, always.
function hash(n) {
  const x = Math.sin(n * 127.1 + 311.7) * 43758.5453
  return x - Math.floor(x)
}

// Half-width of the wet body along the stroke: touches down, swells as the
// bristles flatten, thins as the paint runs out.
function bodyHalfWidth(t) {
  const stops = [
    [0, 1.6],
    [0.1, 6.2],
    [0.3, 8.4],
    [0.52, 7.2],
    [0.72, 4.4],
    [0.88, 2.0],
    [1, 0.6],
  ]
  for (let i = 1; i < stops.length; i += 1) {
    const [t1, w1] = stops[i]
    if (t <= t1) {
      const [t0, w0] = stops[i - 1]
      return w0 + (w1 - w0) * ((t - t0) / (t1 - t0))
    }
  }
  return 0.6
}

/**
 * Build one closed outline along a centreline.
 * `widthAt(t)` gives the half-width; `edge` adds deterministic ragging so the
 * boundary is a bristle edge rather than a drawn curve.
 */
function outline({ ax, ay, dx, dy, nx, ny, bend, from = 0, to = 1, widthAt, edge = 0, seed = 0 }) {
  const left = []
  const right = []
  for (let i = 0; i <= SAMPLES; i += 1) {
    const u = i / SAMPLES
    const t = from + (to - from) * u
    const wobble = Math.sin(t * Math.PI) * bend + Math.sin(t * Math.PI * 2.3) * bend * 0.3
    const cx = ax + dx * t + nx * wobble
    const cy = ay + dy * t + ny * wobble
    const w = widthAt(t)
    // Ragging is applied per side, so the two edges break independently --
    // which is what makes it look like bristles rather than a wavy ribbon.
    const rl = w + (hash(i * 3.1 + seed) - 0.5) * edge
    const rr = w + (hash(i * 5.7 + seed + 99) - 0.5) * edge
    left.push(`${(cx + nx * rl).toFixed(2)},${(cy + ny * rl).toFixed(2)}`)
    right.push(`${(cx - nx * rr).toFixed(2)},${(cy - ny * rr).toFixed(2)}`)
  }
  return `M${left.join('L')}L${right.reverse().join('L')}Z`
}

/** One whole stroke: wet body, drying bristles, thrown flecks. */
function buildStroke(ax, ay, bx, by, bend, seed) {
  const dx = bx - ax
  const dy = by - ay
  const len = Math.hypot(dx, dy)
  const nx = -dy / len
  const ny = dx / len
  const base = { ax, ay, dx, dy, nx, ny, bend }

  const parts = []

  // 1. The wet head, with a lightly broken edge.
  parts.push({
    d: outline({ ...base, widthAt: bodyHalfWidth, edge: 1.5, seed }),
    cls: 'brush-x__body',
  })

  // 2. The bristles. Each sits at its own offset across the brush's width and
  //    starts where that part of the head begins to lift, running past the
  //    body's end -- which is exactly where a real stroke splits.
  const BRISTLES = 7
  for (let k = 0; k < BRISTLES; k += 1) {
    const h = hash(k * 17.3 + seed)
    const h2 = hash(k * 29.1 + seed + 7)
    // Spread across the head's width, biased away from dead centre so the
    // splits read as separate fibres rather than as one thick tail.
    const offset = (k / (BRISTLES - 1) - 0.5) * 11 + (h - 0.5) * 1.6
    const from = 0.42 + h * 0.26
    const to = 1.0 + h2 * 0.18
    const thick = 0.5 + h2 * 0.85
    parts.push({
      d: outline({
        ...base,
        from,
        to,
        // A bristle thins along its own length and vanishes at its tip.
        widthAt: (t) => {
          const u = (t - from) / (to - from)
          return thick * (1 - u) ** 0.85
        },
        edge: 0.5,
        seed: seed + k * 13,
        // Shift the whole sliver off the centreline. `...base` already carries
        // nx/ny; only the origin moves.
        ax: ax + nx * offset,
        ay: ay + ny * offset,
      }),
      cls: 'brush-x__bristle',
    })
  }

  // 3. Flecks thrown past the tail, where the brush finally leaves the paper.
  for (let k = 0; k < 3; k += 1) {
    const h = hash(k * 41.7 + seed + 31)
    const t0 = 1.02 + h * 0.1
    const offset = (hash(k * 53.3 + seed) - 0.5) * 13
    parts.push({
      d: outline({
        ...base,
        from: t0,
        to: t0 + 0.05 + h * 0.05,
        widthAt: () => 0.45 + h * 0.4,
        edge: 0.3,
        seed: seed + k * 71,
        ax: ax + nx * offset,
        ay: ay + ny * offset,
      }),
      cls: 'brush-x__fleck',
    })
  }

  return parts
}

// `className` is ADDITIVE, not a replacement, and that distinction is
// load-bearing: with `className = 'brush-x'` as a default, the only call site
// (`<BrushCross className="collab__x" />`) replaced the base class, so
// `.sheet.is-shown .brush-x` matched nothing and the settle animation written
// for it never ran once. The base class carries the mark's own behaviour; a
// caller's class carries that surface's sizing. Both are needed, so both ship.
// Built once at module scope, not per render: the geometry depends on nothing
// but the constants above it, so a `useMemo` here was memoising a value that
// could never change between renders anyway.
const STROKES = [
  // The SHORT one: made first, brush still fully loaded, so it stays solid and
  // stops early.
  buildStroke(24, 22, 74, 80, 1.8, 3),
  // The LONG one: made second on a drying brush, overshooting the first at both
  // ends -- which is where all the split and the flecks land.
  buildStroke(94, 6, 6, 98, -2.6, 61),
]

export default function BrushCross({ className = '' }) {
  // ASYMMETRIC ON PURPOSE, and this is what stops it reading as a glyph: two
  // strokes of equal length crossing at their midpoints is a multiplication
  // sign, however textured the edges are. A hand makes one confident stroke
  // and then a second that overshoots -- different lengths, different amounts
  // of paint left, crossing well off-centre.
  return (
    <svg
      className={`brush-x ${className}`.trim()}
      viewBox="0 0 100 100"
      aria-hidden="true"
      focusable="false"
    >
      {STROKES.map((parts, s) => (
        <g key={s} className={`brush-x__stroke brush-x__stroke--${s + 1}`}>
          {parts.map((p, i) => (
            <path key={i} className={p.cls} d={p.d} />
          ))}
        </g>
      ))}
    </svg>
  )
}
