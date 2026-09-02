import { useRef, useState } from 'react'

// A file target that is the whole slot, and then a MANIFEST of what was read.
//
// Shape borrowed from extend.ai's file-upload (ui.extend.ai, owner-pinned):
// a lead line, an explicit Browse control, the accepted formats, a label that
// changes while a file is over the target, and per-file rows once something
// has landed. None of its code is here.
//
// What is STITCH's own is what fills those rows. This product's first
// principle is that determinism must be PROVABLE, not asserted (PRODUCT.md),
// and /api/parse-preview already answers with the first few records exactly
// as it read them. So a landed file does not get a filename and a tick: it
// gets the molecules back, each beside what the parser made of it. "I read
// your file" becomes "here is what I read", which is the same move the
// round-trip line makes under every name.
//
// The native input is still the mechanism -- hidden, never replaced -- so the
// label association, the keyboard and the platform picker all behave exactly
// as issued.
//
// Its own component rather than 200 lines inside Home, matching how this
// codebase already factors Switch and ExampleChips: both are used by exactly
// one page and both live here.

// ONE statement of which formats STITCH reads. The picker's `accept`, the
// pattern a DROPPED file is checked against (a drop never passes through
// `accept`), the line on the face and the rejection sentence are all derived
// from this array -- they were four separate literals, and the hint had
// already drifted to three formats while the picker offered five.
// Not exported: nothing outside this file needs it, and a non-component
// export here disables React fast refresh for the whole module.
const ACCEPTED_EXTENSIONS = ['sdf', 'mol', 'csv', 'smi', 'txt']

const ACCEPT_ATTRIBUTE = ACCEPTED_EXTENSIONS.map((ext) => `.${ext}`).join(',')
const ACCEPTED_FILE_RE = new RegExp(`\\.(${ACCEPTED_EXTENSIONS.join('|')})$`, 'i')

/**
 * ".sdf, .mol, .csv, .smi or .txt".
 *
 * OR, not "and". A file is one of these, and "and" read as a list of things
 * you have to supply together. The rejection sentence keeps "or" for the
 * same reason: it is telling you which single format to bring.
 */
function spellOutFormats() {
  const dotted = ACCEPTED_EXTENSIONS.map((ext) => `.${ext}`)
  return `${dotted.slice(0, -1).join(', ')} or ${dotted[dotted.length - 1]}`
}

/**
 * Bytes, in the unit the file manager the file came from would say.
 *
 * Decimal (kB = 1000), not binary: every current desktop platform reports
 * decimal, and a size that disagrees with the reader's own file browser by
 * 2.4% is a small lie for no gain.
 */
function fileSize(bytes) {
  if (!Number.isFinite(bytes)) return null
  if (bytes < 1000) return `${bytes} B`
  if (bytes < 1000 * 1000) return `${Math.round(bytes / 1000)} kB`
  return `${(bytes / 1000 / 1000).toFixed(1)} MB`
}

/**
 * @param inputId   id for the native input.
 * @param file      the currently chosen file, or null. The zone reports the
 *                  choice and displays it; it never owns it.
 * @param preview   the /api/parse-preview response for `file`, or null while
 *                  that request is still in flight.
 * @param onFile    called with a File once one is chosen or dropped.
 * @param onRemove  called when the reader wants the file gone.
 * @param onReject  called with a sentence when a drop cannot be accepted.
 * @param disabled  a submission is in flight; refuse drags entirely.
 */
export default function Dropzone({
  inputId,
  file,
  preview,
  onFile,
  onRemove,
  onReject,
  disabled = false,
}) {
  const [dragging, setDragging] = useState(false)

  // A DEPTH, not a boolean: dragging over a child fires dragleave on the
  // parent, so a boolean flickers the armed state off and on as the pointer
  // crosses the label inside the zone. Counting is also preferred over
  // relatedTarget/contains(), which is unreliable for drag events.
  const dragDepthRef = useRef(0)

  // `dataTransfer.types` is already a frozen array of strings, so it takes
  // .includes() directly -- Array.from() around it allocated a copy on every
  // single dragover, and dragover fires continuously for the whole gesture.
  function isFileDrag(event) {
    if (disabled) return false
    // Only a FILE drag arms the zone: dragging selected text over the card
    // is not an upload.
    return (event.dataTransfer?.types ?? []).includes('Files')
  }

  function handleDragEnter(event) {
    if (!isFileDrag(event)) return
    event.preventDefault()
    dragDepthRef.current += 1
    setDragging(true)
  }

  function handleDragOver(event) {
    if (!isFileDrag(event)) return
    // Without preventDefault on dragover the browser keeps its own default
    // and the drop never reaches the handler below at all.
    event.preventDefault()
    event.dataTransfer.dropEffect = 'copy'
  }

  function handleDragLeave() {
    if (dragDepthRef.current > 0) dragDepthRef.current -= 1
    if (dragDepthRef.current === 0) setDragging(false)
  }

  function handleDrop(event) {
    event.preventDefault()
    dragDepthRef.current = 0
    setDragging(false)
    if (disabled) return
    const dropped = event.dataTransfer?.files
    if (!dropped || dropped.length === 0) return
    if (dropped.length > 1) {
      // One job, one file. Saying so beats silently naming the first of five.
      onReject?.(`One file at a time, please — that was ${dropped.length}.`)
      return
    }
    const chosen = dropped[0]
    // Checked here rather than left to the server: a dropped file bypasses
    // the picker's `accept`, and "unsupported file type" is a better answer
    // than a 400 after a 50 MB upload.
    if (!ACCEPTED_FILE_RE.test(chosen.name)) {
      onReject?.(`STITCH reads ${spellOutFormats()} — "${chosen.name}" is none of those.`)
      return
    }
    onFile(chosen)
  }

  const classes = ['dropzone']
  if (dragging) classes.push('dropzone--armed')
  if (file) classes.push('dropzone--loaded')

  const fileLevelErrors = preview
    ? preview.errors.filter((message) => !preview.sample.some((row) => row.error === message))
    : []

  return (
    <div
      className={classes.join(' ')}
      onDragEnter={handleDragEnter}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {/* The seam. A dashed rule is this system's mark for "provisional" and
          the footer already sews one shut, so an empty target is drawn as a
          seam waiting to be stitched -- and while a file is over it, the
          dashes actually run. That running seam is this system's own answer
          to the reference's travelling border light, in the vocabulary the
          rest of the app already speaks. SVG rather than a dashed border,
          because a border cannot animate its dashes.
          100% of an svg inset by 1px, NOT a rect inset by 1px: width/height
          presentation attributes take a length or a percentage and no
          calc(), and x/y/width/height as CSS properties are not portable.
          The svg carries the inset instead, and overflow: visible lets the
          stroke straddle the path as strokes normally do. */}
      <svg className="dropzone__seam" aria-hidden="true">
        <rect className="dropzone__seam-line" width="100%" height="100%" rx="13" />
      </svg>

      <input
        id={inputId}
        className="dropzone__input"
        type="file"
        accept={ACCEPT_ATTRIBUTE}
        onChange={(event) => onFile(event.target.files?.[0] ?? null)}
        disabled={disabled}
      />

      {file ? (
        /* THE MANIFEST. Not a label, and that is deliberate: Remove must not
           reopen the picker, so the actions sit outside any label and
           Replace is a label of its own. Dropping anywhere on the zone still
           replaces the file, because the drag handlers are on the container. */
        <div className="dropzone__manifest">
          <header className="dropzone__manifest-head">
            <span className="dropzone__file-name">{file.name}</span>
            <span className="dropzone__file-meta">
              {[
                fileSize(file.size),
                preview
                  ? `${preview.molecule_count} molecule${preview.molecule_count === 1 ? '' : 's'}`
                  : 'reading…',
                preview ? `read as ${preview.format}` : null,
              ]
                .filter(Boolean)
                .join('  ·  ')}
            </span>
            <span className="dropzone__manifest-actions">
              <label htmlFor={inputId} className="dropzone__action">
                Replace
              </label>
              <button
                type="button"
                className="dropzone__action"
                onClick={onRemove}
                disabled={disabled}
              >
                Remove
              </button>
            </span>
          </header>

          {preview && (
            <>
              {/* WHAT IT ACTUALLY READ. Left is your line, right is what the
                  parser made of it -- the same "here is the proof" move the
                  round-trip line makes under a name.
                  These rows deliberately carry NO confidence mark: a preview
                  row has no tier (ParsePreviewRow in schemas.py says so
                  outright, and says why), and borrowing the rule grammar here
                  would draw an abstain's rule under a molecule that nothing
                  has judged yet. */}
              <ol className="dropzone__rows">
                {preview.sample.map((row) => (
                  <li className="dropzone__row" key={`${row.index}-${row.input}`}>
                    <span className="dropzone__row-n">{String(row.index + 1).padStart(2, '0')}</span>
                    <code className="dropzone__row-in" title={row.input}>
                      {row.input_id ? `${row.input_id} · ` : ''}
                      {row.input}
                    </code>
                    <span className="dropzone__row-arrow" aria-hidden="true" />
                    {row.smiles ? (
                      <code className="dropzone__row-out">{row.smiles}</code>
                    ) : (
                      <span className="dropzone__row-out dropzone__row-out--failed">
                        {row.error || 'could not be read'}
                      </span>
                    )}
                  </li>
                ))}
              </ol>

              {/* Only the errors NO row is already showing. preview.errors
                  and the rows' own `error` fields overlap: a bad record puts
                  the same sentence in both, and printing it twice was the
                  first thing the manifest got wrong. What survives the
                  filter is the file-level complaint -- a missing smiles
                  column, say -- which has no row to sit on. */}
              {fileLevelErrors.length > 0 && (
                <ul className="dropzone__errors">
                  {fileLevelErrors.map((message) => (
                    <li key={message}>{message}</li>
                  ))}
                </ul>
              )}

              {/* This wording is deliberate and must not be softened to "no
                  errors found". The server parses only the first few records,
                  so a clean preview says nothing about row 6 --
                  ParsePreviewResponse's own docstring calls out that this
                  endpoint has never validated a whole file. */}
              <p className="dropzone__caveat">
                Checked the first {preview.sample.length} record
                {preview.sample.length === 1 ? '' : 's'} only — later rows may still fail.
              </p>
            </>
          )}
        </div>
      ) : (
        <label htmlFor={inputId} className="dropzone__face">
          {/* THE PLATE. A stack of rounded plates (two drawn by CSS behind
              this one) holding STITCH's OWN mark: the same two-atom bond the
              header and footer wear. The reference puts a generic upload
              glyph here; a target that only ever accepts molecules should
              say molecules. Ink, not crimson -- this card already spends the
              one accent on Start job and on the info lamp, and a third
              would stop the accent meaning "act here". */
          }
          <span className="dropzone__plate" aria-hidden="true">
            <svg viewBox="0 0 32 32" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round">
              <line x1="11" y1="21" x2="21" y2="11" />
              <circle cx="8" cy="24" r="3.5" fill="currentColor" stroke="none" />
              <circle cx="24" cy="8" r="3.5" fill="currentColor" stroke="none" />
            </svg>
          </span>

          {/* The lead SPEAKS THE STATE: while a file is over the target it
              stops describing the target and starts describing what happens
              when you let go. */}
          <span className="dropzone__lead">
            {dragging ? 'Release to read it' : 'Click to upload, or drop a file'}
          </span>

          {/* The accepted formats as a SENTENCE, from the same array the
              picker and the drop check use. As a mono list joined by
              middots it read like data the reader had to parse. */}
          <span className="dropzone__formats">{spellOutFormats()}</span>

          {/* A span, not a button: a <button> inside a <label> does not
              activate that label's input, and this is the one control on the
              face whose whole job is to open the picker. Quiet by design --
              the card's one primary action is Start job. */}
          <span className="dropzone__browse">
            <svg
              className="dropzone__browse-icon"
              viewBox="0 0 16 16"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinecap="round"
              aria-hidden="true"
            >
              <line x1="8" y1="11" x2="8" y2="2" />
              <path d="M4.6 5.4 8 2l3.4 3.4" />
              <line x1="2.5" y1="13.5" x2="13.5" y2="13.5" />
            </svg>
            Browse files
          </span>

          <span className="dropzone__note">
            In a .csv, name the column <code>smiles</code>. In a plain list, one SMILES per line.
          </span>
        </label>
      )}
    </div>
  )
}
