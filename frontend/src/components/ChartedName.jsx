/**
 * The product's name, cross-stitched: S T I T C H, charted cell by cell.
 *
 * The page's signature. A cross-stitch chart is a grid where each occupied
 * square carries a symbol, and a sampler — the first thing anyone stitches —
 * is letters worked exactly that way. So this is not a decorative flourish
 * borrowed from the world: it is the single most ordinary object in it,
 * spelling the thing the site is called.
 *
 * It replaced a charted benzene ring (owner instruction, 2026-09-06). The ring
 * was the better joke; this is the better cover, and it is better for a reason
 * worth recording: at 35 cells wide it is a BAND, so it fills the plate's full
 * measure instead of competing with the title for a column. Three attempts at
 * that two-column layout each measured a 300-400px hole down the middle of the
 * plate; a full-width band cannot leave one.
 *
 * Drawn from a plotted glyph map rather than from letterforms, because that is
 * what makes it a chart: the shape is a list of occupied cells exactly as a
 * pattern prints it, and the stitch in each cell is worked on top. Setting the
 * word in a display face and calling it charted would be a picture of a
 * sampler rather than a sampler.
 */

// A 5x7 charted alphabet — only the letters this word needs. '#' is a worked
// cell. Hand-plotted, and kept as text so the shapes can be read and corrected
// in place rather than decoded from coordinates.
const GLYPHS = {
  S: ['.####', '#....', '#....', '.###.', '....#', '....#', '####.'],
  T: ['#####', '..#..', '..#..', '..#..', '..#..', '..#..', '..#..'],
  I: ['#####', '..#..', '..#..', '..#..', '..#..', '..#..', '#####'],
  C: ['.###.', '#...#', '#....', '#....', '#....', '#...#', '.###.'],
  H: ['#...#', '#...#', '#...#', '#####', '#...#', '#...#', '#...#'],
}

const WORD = 'STITCH'
const GLYPH_H = 7
const GAP = 1 // one empty column between letters, as a sampler leaves
const CELL = 10

// Compose the word into one row-major plot, so the renderer below only has to
// know about cells and never about letters.
function plotWord(word) {
  const rows = Array.from({ length: GLYPH_H }, () => [])
  word.split('').forEach((ch, i) => {
    const glyph = GLYPHS[ch]
    for (let y = 0; y < GLYPH_H; y += 1) {
      if (i > 0) for (let g = 0; g < GAP; g += 1) rows[y].push('.')
      rows[y].push(...glyph[y].split(''))
    }
  })
  return rows.map((r) => r.join(''))
}

// Plotted once at module scope. WORD and GLYPHS are constants, so the plot is
// the same array on every render and a `useMemo` was guarding a value that had
// no way to change.
const PLOT = plotWord(WORD)
const COLS = PLOT[0].length

export default function ChartedName({ className = 'charted' }) {
  const plot = PLOT
  const cols = COLS

  // ROW-MAJOR, and the order is the point: a cross-stitcher works a row left
  // to right, then drops to the next. `n` counts the worked cells in that
  // order and drives the stagger, so the piece appears the way it would
  // actually be sewn rather than in a scatter or a plain column wipe.
  const stitches = []
  let n = 0
  for (let y = 0; y < GLYPH_H; y += 1) {
    for (let x = 0; x < cols; x += 1) {
      if (plot[y][x] !== '#') continue
      const order = n
      n += 1
      const cx = x * CELL
      const cy = y * CELL
      // The cross is inset inside its square so each stitch stays its own
      // mark. Without the inset the crosses touch and the word reads as a
      // solid outline, which is a stencil rather than a stitched sampler.
      stitches.push(
        <g key={`${x}-${y}`} className="charted__stitch" style={{ '--n': order }}>
          {/* TWO STROKES, because that is what a cross stitch is: the needle
              lays one diagonal, comes back up, and crosses it. They are drawn
              in that order, each pulled on from its own starting hole, so the
              stitch is made rather than faded in. */}
          <line
            className="charted__leg charted__leg--first"
            x1={cx + 1.8}
            y1={cy + 1.8}
            x2={cx + CELL - 1.8}
            y2={cy + CELL - 1.8}
          />
          <line
            className="charted__leg charted__leg--second"
            x1={cx + CELL - 1.8}
            y1={cy + 1.8}
            x2={cx + 1.8}
            y2={cy + CELL - 1.8}
          />
        </g>
      )
    }
  }

  return (
    <svg
      className={className}
      viewBox={`0 0 ${cols * CELL} ${GLYPH_H * CELL}`}
      role="img"
      aria-label="STITCH, worked as a cross-stitch sampler"
      focusable="false"
    >
      {/* The squared ground, drawn as real lines at the same cell pitch as the
          plate behind it, so the band sits ON the page's grid rather than
          carrying a second one of its own. */}
      <g className="charted__grid" aria-hidden="true">
        {Array.from({ length: cols + 1 }, (_, i) => (
          <line key={`v${i}`} x1={i * CELL} y1={0} x2={i * CELL} y2={GLYPH_H * CELL} />
        ))}
        {Array.from({ length: GLYPH_H + 1 }, (_, i) => (
          <line key={`h${i}`} x1={0} y1={i * CELL} x2={cols * CELL} y2={i * CELL} />
        ))}
      </g>
      {stitches}
    </svg>
  )
}
