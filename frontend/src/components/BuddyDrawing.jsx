// Kekunyo, the buddy: a puffy benzene ring wearing the Orthonym element
// label, with atom hands and tiny feet. Picked from a lineup of 24 and named
// by the owner on 2026-09-28. The name is internal: nothing on the site
// shows it. One drawing for both places it appears -- behind the issue tab
// (IssueBuddy.jsx) and roaming the About page (BuddyRoam.jsx) -- and its
// classes (`ib-*`) are styled and animated in App.css.

function Eye({ x, y }) {
  return (
    <>
      <circle className="ib-ink" cx={x} cy={y} r="5.2" />
      <circle className="ib-white" cx={x + 2} cy={y - 2} r="2.2" />
      <circle className="ib-white" cx={x - 1.8} cy={y + 2.1} r="1" />
    </>
  )
}

function HappyEye({ x, y }) {
  return <path className="ib-line" d={`M${x - 4.8} ${y + 1.5} Q${x} ${y - 5} ${x + 4.8} ${y + 1.5}`} />
}

function Spark({ x, y, size, delay }) {
  const k = size * 0.28
  const d =
    `M${x} ${y - size} Q${x + k} ${y - k} ${x + size} ${y} Q${x + k} ${y + k} ${x} ${y + size} ` +
    `Q${x - k} ${y + k} ${x - size} ${y} Q${x - k} ${y - k} ${x} ${y - size} Z`
  return <path className="ib-spark" style={{ '--d': `${delay}ms` }} d={d} />
}

export default function BuddyDrawing() {
  return (
    <svg viewBox="0 0 100 100" aria-hidden="true" focusable="false">
      <g className="ib-body">
        <ellipse className="ib-ink" cx="39" cy="89" rx="6.5" ry="3.6" />
        <ellipse className="ib-ink" cx="61" cy="89" rx="6.5" ry="3.6" />
        <g className="ib-hold">
          <line className="ib-stroke" x1="21" y1="54" x2="8" y2="48" />
          <circle className="ib-stroke ib-atom" cx="6" cy="46" r="5.5" />
        </g>
        <g className="ib-wave">
          <line className="ib-stroke" x1="79" y1="50" x2="92" y2="38" />
          <circle className="ib-stroke ib-atom" cx="94" cy="35" r="5.5" />
        </g>
        <path
          className="ib-stroke ib-shell"
          d="M50 20 Q53 20 79 35 Q82 37 82 41 V65 Q82 69 79 71 L53 85 Q50 87 47 85 L21 71 Q18 69 18 65 V41 Q18 37 21 35 L47 20 Q50 19 50 20 Z"
        />
        <text className="ib-number" x="31" y="45">1</text>
        <text className="ib-symbol" x="50" y="45">Or</text>
        <g className="ib-eyes ib-face-open">
          <Eye x={39} y={56} />
          <Eye x={61} y={56} />
        </g>
        <g className="ib-face-happy">
          <HappyEye x={39} y={56} />
          <HappyEye x={61} y={56} />
        </g>
        <ellipse className="ib-cheek" cx="28" cy="64" rx="5" ry="3.4" />
        <ellipse className="ib-cheek" cx="72" cy="64" rx="5" ry="3.4" />
        <path className="ib-line ib-smile" d="M46 64 Q50 68 54 64" />
        <g className="ib-mouth-open">
          <path className="ib-ink" d="M45 63 Q50 73 55 63 Z" />
          <ellipse className="ib-atom" cx="50" cy="67.4" rx="2.4" ry="1.8" />
        </g>
        <text className="ib-label" x="50" y="75">ORTHONYM</text>
      </g>
      <Spark x={92} y={16} size={5.5} delay={120} />
      <Spark x={8} y={74} size={4.5} delay={420} />
      <Spark x={96} y={72} size={4} delay={760} />
    </svg>
  )
}
