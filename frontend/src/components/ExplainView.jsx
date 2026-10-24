import { Fragment, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { verdictKindFor } from '../lib/explainVerdict'
import { isPart, partOf, sliceName, unplacedNodes } from '../lib/nameTargets'
import { detailNotes, pieceMark, tabStops } from '../lib/explainView'
import { nameRuns, applyRuns } from '../lib/nameTypography'
import { useAtomHighlight } from '../lib/useAtomHighlight'
import { TIER_SETTINGS } from '../lib/useExplain'
import ConfidenceReport from './ConfidenceReport'
import ReportLink from './ReportLink'
import ShareButton from './ShareButton'
import ChemName, { Pieces } from './Typeset'

/**
 * One explained name: the name as a hover surface, the parts OPSIN gave no
 * position, the confidence tier (or the "you supplied this name" note), the
 * picture with its lit atoms, and the detail panel. Moved out of Explain.jsx
 * unchanged so /compare can show two.
 *
 * It owns its own hover and pin. The page renders it with a `key` per result,
 * so both reset on each new answer, as Explain's runExplain used to reset them.
 *
 * `marks` (/compare): a Set of node ids the other name does not have. A
 * marked part gets a grey highlight and a spoken "differs" -- never a line,
 * because every line style under a name is already a confidence tier.
 *
 * Classroom mode (/explain): `hidden` is a Set of node ids not yet revealed;
 * their pieces render as dots, with no text in the DOM. `forcedId` lights the
 * newest revealed part. The tier waits until nothing is hidden. `afterName`
 * is a slot under the name for the step controls.
 */
export default function ExplainView({
  data,
  resultMode,
  tierRow,
  apiError,
  shareFields,
  marks = null,
  hidden = null,
  forcedId = null,
  afterName = null,
}) {
  const [hoveredId, setHoveredId] = useState(null)
  const [pinnedId, setPinnedId] = useState(null)
  const activeId = forcedId ?? pinnedId ?? hoveredId
  // Classroom mode: some parts are still hidden. Nothing on screen or in the
  // accessibility tree may give their text away.
  const veiled = Boolean(hidden?.size)

  function toggleId(id) {
    setPinnedId((current) => (current === id ? null : id))
  }

  // The handlers a name piece and an unplaced-part button share: hover or focus
  // previews a node, click pins it.
  function hoverProps(id) {
    return {
      onMouseEnter: () => setHoveredId(id),
      onMouseLeave: () => setHoveredId(null),
      onFocus: () => setHoveredId(id),
      onBlur: () => setHoveredId(null),
      onClick: () => toggleId(id),
    }
  }

  const svgWrapperRef = useAtomHighlight(data, activeId)
  const name = data?.name
  const nodes = useMemo(() => data?.nodes || [], [data])
  const byId = useMemo(() => new Map(nodes.map((node) => [node.id, node])), [nodes])
  // Every part node has a span (the corpus gate proves it), so the name is
  // always the hover surface. Nodes OPSIN gave no position are listed under
  // it instead of blanking anything (per-node honesty).
  const unplaced = unplacedNodes(nodes)
  const nameStyle = name ? nameRuns(name) : []
  const activeNode = byId.get(activeId) ?? null
  const activePart = partOf(nodes, activeId)
  const notes = detailNotes(nodes, activeId)
  const pieces = name ? sliceName(name, nodes) : []
  const stops = tabStops(pieces)

  return (
    <div className="explain-result">
      <div className="explain-result__name-row">
        <span className="explain-result__name-label">Name</span>
        {name && (
          <p className="explain-result__name explain-name" aria-live="polite">
            {pieces.map((piece, index) => {
              const node = byId.get(piece.nodeId) ?? null
              const mark = pieceMark(piece, activeId, activePart)
              return (
                <Fragment key={index}>
                  {index > 0 && /[)\]},]/.test(name[piece.start - 1] || '') &&
                    !'-,)]}'.includes(name[piece.start] || 'x') && <wbr />}
                  {node !== null && hidden?.has(node.id) ? (
                    <span className="explain-name__part explain-name__part--hidden" role="img" aria-label="Hidden part">
                      {'·'.repeat(piece.end - piece.start)}
                    </span>
                  ) : node === null ? (
                    <span><Pieces pieces={applyRuns(name, nameStyle, piece.start, piece.end)} /></span>
                  ) : (
                    <span
                      className={`explain-name__part${isPart(node) ? '' : ' explain-name__part--ref'}${
                        mark ? ` explain-name__part--${mark}` : ''
                      }${marks?.has(node.id) ? ' explain-name__part--differs' : ''}`}
                      {...hoverProps(node.id)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter' || event.key === ' ') {
                          event.preventDefault()
                          toggleId(node.id)
                        }
                      }}
                      tabIndex={stops.has(index) ? 0 : -1}
                      role="button"
                      aria-label={marks?.has(node.id) ? `${node.label}, differs` : node.label}
                      aria-pressed={pinnedId === node.id}
                    >
                      <Pieces pieces={applyRuns(name, nameStyle, piece.start, piece.end)} breaks={false} />
                    </span>
                  )}
                </Fragment>
              )
            })}
            {shareFields && <ShareButton fields={shareFields} />}
          </p>
        )}
        {afterName}
        {unplaced.some((node) => !hidden?.has(node.id)) && (
          <ul className="explain-unplaced" role="list" aria-label="Parts not placed in the name">
            {unplaced.filter((node) => !hidden?.has(node.id)).map((node) => (
              <li key={node.id}>
                <button
                  type="button"
                  className={`explain-unplaced__item${activeId === node.id ? ' explain-unplaced__item--active' : ''}${
                    marks?.has(node.id) ? ' explain-name__part--differs' : ''
                  }`}
                  {...hoverProps(node.id)}
                  aria-pressed={pinnedId === node.id}
                >
                  {node.label} <span className="explain-unplaced__note">— not placed in the name</span>
                  {marks?.has(node.id) && <span className="sr-only">, differs</span>}
                </button>
              </li>
            ))}
          </ul>
        )}
        {/* /api/explain returns the name and its decomposition but
            no confidence tier. For a STRUCTURE the tier is a real
            Orthonym verdict, so runExplain fetches it from
            /api/translate alongside and it is shown here -- PRODUCT.md
            principle 3 requires it wherever a name appears.

            For a name the USER typed there is no verdict to report:
            Orthonym did not produce that name, so it has no opinion on
            whether it is a PIN. Saying so plainly is the honest
            option; inventing a tier mark would misrepresent
            confidence, which the product forbids. */}
        {veiled ? null : verdictKindFor(resultMode) === 'user-supplied' ? (
          <p className="explain-tier-note">
            This breakdown is of the name <em>you</em> supplied, so there is no
            Orthonym confidence tier for it. Draw or paste a structure instead, or
            run the molecule through{' '}
            <Link to="/" className="about-link">
              Translate
            </Link>
            , to see whether Orthonym&rsquo;s own name for it is a verified PIN, a
            fallback, or a best effort.
          </p>
        ) : (
          <ConfidenceReport row={tierRow} />
        )}
      </div>

      {/* A partial result is a real case (see runExplain): the backend
          can name and draw a molecule and still fail to decompose that
          name, and it then carries `error` alongside `name`/`svg`.
          Shown as a notice rather than a blocking error, so nothing
          that WAS drawn gets hidden. */}
      {apiError && (
        <p className="notice" role="status">
          {apiError}
        </p>
      )}
      {/* A success phase can still be a molecule Orthonym would not
          name: uranium trioxide lands here with a drawn structure and
          an abstain tier row, not in the error branch. */}
      {!veiled && <ReportLink row={tierRow} where="Explain" settings={TIER_SETTINGS} />}

      {(data?.svg || nodes.length > 0) && (
        <div className="explain-result__body">
          {data?.svg && (
            <div
              className="explain-result__diagram"
              role="img"
              aria-label={veiled ? '2D structure diagram' : `2D structure diagram of ${name}`}
              ref={svgWrapperRef}
            />
          )}

          {nodes.length > 0 && (
            <div className="explain-detail">
              {activeNode ? (
                <>
                  <h3 className="explain-detail__label">
                    <ChemName name={activeNode.label} />
                  </h3>
                  <p className="explain-detail__explanation">{activeNode.line}</p>
                  {/* Classroom mode: naming a part still hidden would give it away. */}
                  {notes.partLabel && !(activePart && hidden?.has(activePart.id)) && (
                    <p className="explain-detail__note">
                      Part of <ChemName name={notes.partLabel} />.
                    </p>
                  )}
                  {notes.notation && (
                    <p className="explain-detail__note">
                      Notation — it points at atoms, and names none of its own.
                    </p>
                  )}
                  {notes.nothingLights && (
                    <p className="explain-detail__note">
                      Nothing lights up: Orthonym points to no single atom for it.
                    </p>
                  )}
                  {notes.unmapped && (
                    <p className="explain-detail__note">
                      Orthonym could not pin this part to exact atoms in this structure, so nothing lights up. The rest of the name is unaffected.
                    </p>
                  )}
                </>
              ) : (
                <p className="explain-detail__hint">
                  Move your pointer across the name above to see what each part means.
                </p>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
