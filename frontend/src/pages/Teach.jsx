import { useState } from 'react'
import { Link } from 'react-router-dom'
import { explainMolecule } from '../lib/api'
import { nameTargets, sliceName } from '../lib/nameTargets'
import { segmentAtPath } from '../lib/svgHighlight'
import { useAtomHighlight } from '../lib/useAtomHighlight'
import { useKetcher } from '../lib/useKetcher'
import './Teach.css'

function Teach() {
  const { iframeRef, editorState, handleFrameLoad, handleFrameError, getKetcher } = useKetcher()
  const [phase, setPhase] = useState('idle') // idle | working | done | failed
  const [data, setData] = useState(null)
  const [note, setNote] = useState(null)
  const [hoveredPath, setHoveredPath] = useState(null)
  const [pinnedPath, setPinnedPath] = useState(null)
  const activePath = pinnedPath ?? hoveredPath

  async function handleName() {
    if (phase === 'working') return
    setNote(null)
    setPinnedPath(null)
    setHoveredPath(null)
    const ketcher = getKetcher()
    if (!ketcher) {
      setNote('The drawing area is still starting up. Give it a moment and try again.')
      return
    }
    let structure = ''
    try {
      structure = (await ketcher.getSmiles()) || ''
    } catch {
      setNote('Could not read your drawing. Try drawing it again.')
      return
    }
    structure = structure.trim()
    if (!structure) {
      setNote('Draw a molecule first, then press Name it.')
      return
    }
    setPhase('working')
    try {
      const result = await explainMolecule(structure)
      setData(result)
      setPhase(result.name ? 'done' : 'failed')
    } catch {
      setNote('Could not reach the naming service. Check it is running and try again.')
      setPhase('idle')
    }
  }

  const svgWrapperRef = useAtomHighlight(data, activePath)

  return (
    <>
      <div className="page-head page-shell">
        <h1 className="page-head__title">Draw it, learn its name</h1>
        <p className="page-head__lede">
          Draw a structure and press Name it. You get the name, and you can point at any part of
          the name to see which atoms it describes.
        </p>
      </div>

      <main className="workspace workspace--draw" aria-label="Learn a name">
        <section className="teach__draw">
          {editorState === 'error' ? (
            <p className="teach__editor-error" role="alert">
              The drawing area did not load. Reload the page to try again.
            </p>
          ) : (
            <iframe
              ref={iframeRef}
              title="Molecule drawing area"
              className="teach__editor"
              src="/standalone/index.html"
              onLoad={handleFrameLoad}
              onError={handleFrameError}
            />
          )}
          <button
            type="button"
            className="btn"
            onClick={handleName}
            disabled={editorState !== 'ready' || phase === 'working'}
          >
            {phase === 'working' ? 'Working…' : 'Name it'}
          </button>
          {note && (
            <p className="teach__note" role="status">
              {note}
            </p>
          )}
        </section>

        <section className="teach__output" aria-label="Result">
          {phase === 'done' && data && (
            <div className="teach__result">
              <p className="teach__name" aria-live="polite">
                {(() => {
                  const segments = data.segments || []
                  const spansAvailable =
                    segments.length > 0 && segments.every((s) => s.name_range)
                  if (!spansAvailable) return data.name
                  return sliceName(data.name, nameTargets(segments)).map((piece, index) =>
                    piece.path === null ? (
                      <span key={index}>{piece.text}</span>
                    ) : (
                      <span
                        key={index}
                        className={`teach__part${
                          activePath === piece.path ? ' teach__part--active' : ''
                        }`}
                        onMouseEnter={() => setHoveredPath(piece.path)}
                        onMouseLeave={() => setHoveredPath(null)}
                        onFocus={() => setHoveredPath(piece.path)}
                        onBlur={() => setHoveredPath(null)}
                        onClick={() =>
                          setPinnedPath((c) => (c === piece.path ? null : piece.path))
                        }
                        onKeyDown={(event) => {
                          if (event.key === 'Enter' || event.key === ' ') {
                            event.preventDefault()
                            setPinnedPath((c) => (c === piece.path ? null : piece.path))
                          }
                        }}
                        tabIndex={0}
                        role="button"
                        aria-pressed={pinnedPath === piece.path}
                      >
                        {piece.text}
                      </span>
                    )
                  )
                })()}
              </p>

              {/* /api/explain carries no confidence tier, so this route
                  cannot show one. Say so rather than invent a mark. */}
              <p className="teach__tier-note">
                This shows how the name breaks down. It does not check the name&rsquo;s
                confidence tier &mdash; run the same molecule through{' '}
                <Link to="/" className="about-link">
                  Translate
                </Link>{' '}
                to see whether it is a verified PIN, a fallback, or a best effort.
              </p>

              <div className="teach__body">
                <div className="teach__structure" ref={svgWrapperRef} />
                <div className="teach__detail">
                  {segmentAtPath(data.segments || [], activePath) ? (
                    <>
                      <h2 className="teach__detail-label">
                        {segmentAtPath(data.segments, activePath).label}
                      </h2>
                      <p>{segmentAtPath(data.segments, activePath).explanation}</p>
                    </>
                  ) : (
                    <p className="teach__hint">
                      Point at any part of the name above to see what it means.
                    </p>
                  )}
                </div>
              </div>

              <ol className="teach__parts">
                {(data.segments || []).map((segment, index) => (
                  <li key={index}>
                    <strong>{segment.label}</strong>
                    <span>{segment.explanation}</span>
                  </li>
                ))}
              </ol>
            </div>
          )}

          {phase === 'failed' && (
            <p className="teach__note" role="status">
              We could not work out a name for that molecule with confidence, so we are
              not going to guess. Try a simpler structure.
            </p>
          )}

          {(phase === 'idle' || phase === 'working') && !note && (
            <p className="teach__empty-note">
              Draw a molecule and press Name it to see its name here.
            </p>
          )}
        </section>
      </main>
    </>
  )
}

export default Teach
