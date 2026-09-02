import { useRef, useState } from 'react'

// A file target that is the whole slot, not a button in the corner of one.
//
// It replaced a bare native `Choose File`, which had two problems: nothing
// said a file could be dragged, and a drag from a file manager had nowhere
// to land. The native input is still the mechanism -- hidden, never replaced
// -- so the label association, the keyboard and the platform picker all
// behave exactly as issued.
//
// Its own component rather than 115 lines inside Home, matching how this
// codebase already factors Switch and ExampleChips: both are used by exactly
// one page and both live here.

// ONE statement of which formats STITCH reads. The picker's `accept`, the
// pattern a DROPPED file is checked against (a drop never passes through
// `accept`), the pills on the face and the rejection sentence are all
// derived from this array -- they were four separate literals, and the
// hint had already drifted to three formats while the picker offered five.
// Not exported: nothing outside this file needs it, and a non-component
// export here disables React fast refresh for the whole module.
const ACCEPTED_EXTENSIONS = ['sdf', 'mol', 'csv', 'smi', 'txt']

const ACCEPT_ATTRIBUTE = ACCEPTED_EXTENSIONS.map((ext) => `.${ext}`).join(',')
const ACCEPTED_FILE_RE = new RegExp(`\\.(${ACCEPTED_EXTENSIONS.join('|')})$`, 'i')

/** ".sdf, .mol, .csv, .smi and .txt" — for a sentence, not a list. */
function spellOutFormats() {
  const dotted = ACCEPTED_EXTENSIONS.map((ext) => `.${ext}`)
  return `${dotted.slice(0, -1).join(', ')} and ${dotted[dotted.length - 1]}`
}

/**
 * @param inputId   id for the native input, so a caller's own <label> can
 *                  point at it too.
 * @param file      the currently chosen file, or null. The zone reports the
 *                  choice and displays it; it never owns it.
 * @param onFile    called with a File once one is chosen or dropped.
 * @param onReject  called with a sentence when a drop cannot be accepted.
 * @param disabled  a submission is in flight; refuse drags entirely.
 */
export default function Dropzone({ inputId, file, onFile, onReject, disabled = false }) {
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

  return (
    <div
      className={`dropzone${dragging ? ' dropzone--armed' : ''}${file ? ' dropzone--loaded' : ''}`}
      onDragEnter={handleDragEnter}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {/* The seam. A dashed rule is this system's mark for "provisional" and
          the footer already sews one shut, so an empty target is drawn as a
          seam waiting to be stitched -- and while a file is over it, the
          dashes actually run. SVG rather than a dashed border because a
          border cannot animate its dashes.
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
      <label htmlFor={inputId} className="dropzone__face">
        <span className="dropzone__mark" aria-hidden="true">
          <span className="dropzone__mark-stroke" />
          <span className="dropzone__mark-stroke" />
          <span className="dropzone__mark-stroke" />
        </span>
        <span className="dropzone__lead">{file ? file.name : 'Drop a file here'}</span>
        <span className="dropzone__sub">
          {file ? 'Drop another to replace it' : 'or click to choose one'}
        </span>
        <span className="dropzone__formats">
          {ACCEPTED_EXTENSIONS.map((ext) => (
            <code key={ext}>.{ext}</code>
          ))}
        </span>
        <span className="dropzone__note">
          A <code>.csv</code> needs a <code>smiles</code> column; a plain list wants one SMILES
          per line.
        </span>
      </label>
    </div>
  )
}
