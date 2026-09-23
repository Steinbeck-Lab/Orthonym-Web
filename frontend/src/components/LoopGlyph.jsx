import { useId } from 'react'

/**
 * The round-trip loop at icon size, so the lower half of the About page can
 * point back at the big one: how far a tier's line gets (`reach`, 0..1, the
 * four stations sitting at 0, 1/4, 1/2 and 3/4 of the way round), which
 * stations a route or a credit runs (`nodes`), and the tier's own rule pattern
 * on the line (`pattern`). A line that stops short ends in an empty ring
 * (the live loop shows that ring on the phone rail; on desktop its line ends
 * under the station tile).
 *
 * The rectangle is symmetric and the line starts at station 1 (left, middle),
 * so every station falls on an exact quarter of the perimeter.
 */
const W = 56
const H = 36
const X0 = 4
const Y0 = 4
const X1 = W - 4
const Y1 = H - 4
const R = 8
const PATH =
  `M ${X0} ${H / 2} V ${Y0 + R} A ${R} ${R} 0 0 1 ${X0 + R} ${Y0} H ${X1 - R} ` +
  `A ${R} ${R} 0 0 1 ${X1} ${Y0 + R} V ${Y1 - R} A ${R} ${R} 0 0 1 ${X1 - R} ${Y1} ` +
  `H ${X0 + R} A ${R} ${R} 0 0 1 ${X0} ${Y1 - R} Z`
const STATIONS = [
  { x: X0, y: H / 2 },
  { x: W / 2, y: Y0 },
  { x: X1, y: H / 2 },
  { x: W / 2, y: Y1 },
]

export default function LoopGlyph({ reach = 0, nodes = [], pattern = 'solid' }) {
  const mask = useId()
  const stop = reach > 0 && reach < 1 ? STATIONS[Math.round(reach * 4)] : null

  return (
    <svg
      className={`loop-glyph loop-glyph--${pattern}`}
      viewBox={`0 0 ${W} ${H}`}
      width={W}
      height={H}
      aria-hidden="true"
    >
      <path className="loop-glyph__route" d={PATH} />
      {reach > 0 && (
        <>
          <mask id={mask} maskUnits="userSpaceOnUse" x="0" y="0" width={W} height={H}>
            <path
              d={PATH}
              fill="none"
              stroke="#fff"
              strokeWidth="8"
              pathLength="1"
              strokeDasharray={`${reach} 1`}
            />
          </mask>
          <g mask={`url(#${mask})`}>
            <path className="loop-glyph__line" d={PATH} pathLength="100" />
            {pattern === 'pin' && <path className="loop-glyph__inner" d={PATH} />}
          </g>
        </>
      )}
      {STATIONS.map((s, i) => (
        <circle
          key={i}
          className={`loop-glyph__node${nodes.includes(i + 1) ? ' is-on' : ''}`}
          cx={s.x}
          cy={s.y}
          r="3.2"
        />
      ))}
      {stop && <circle className="loop-glyph__stop" cx={stop.x} cy={stop.y} r="4.6" />}
    </svg>
  )
}
