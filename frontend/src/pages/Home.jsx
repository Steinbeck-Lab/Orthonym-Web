import { useEffect, useMemo, useRef, useState } from 'react'
import ExampleChips from '../components/ExampleChips'
import SamplerGrid from '../components/SamplerGrid'
import ConfidenceLegend from '../components/ConfidenceLegend'
import BatchResults from '../components/BatchResults'
import Switch from '../components/Switch'
import {
  createJob,
  fetchExamples,
  parsePreview,
  translateBatch,
  TranslateJobQueuedError,
} from '../lib/api'
import { needsJob } from '../lib/batchJob'
import { forgetJob, readJobs, rememberJob } from '../lib/jobStore'
import { MAX_ROWS, parseSmilesLines } from '../lib/parseSmiles'
import useKetcher from '../lib/useKetcher'
import useReducedMotion from '../lib/useReducedMotion'
import './Home.css'

// The same set the file picker's `accept` offers, as a pattern, because a
// DROPPED file never passes through `accept` at all. Kept beside it in the
// markup so the two cannot drift.
const ACCEPTED_FILE_RE = /\.(sdf|mol|csv|smi|txt)$/i

function emptyRow(smiles) {
  return {
    smiles,
    phase: 'pending',
    status: null,
    name: null,
    tier: null,
    formula: null,
    limit_code: null,
    error: null,
    depiction_svg: null,
    roundtrip_smiles: null,
    roundtrip_match: null,
  }
}

// WebGPU flare states: 'off' (unsupported, refused, or reduced motion -- no
// canvas in the DOM at all), 'pending' (canvas mounted, GPU still starting),
// 'live' (drawing). 'off' is also where a failure lands, so a broken driver
// degrades to the plain wordmark instead of an empty box.
function useWordmarkFlare(reduceMotion) {
  const canvasRef = useRef(null)
  const wordmarkRef = useRef(null)
  // Three pieces of state, deliberately not one: `mounted` decides whether the
  // canvas exists, and it is the ONLY thing the renderer effect may depend on.
  // `live` and `failed` are results, and they must never re-run that effect --
  // an earlier version kept a single 'off' | 'pending' | 'live' state and put
  // it in the dependency array, so setting 'live' re-ran the effect, whose
  // cleanup disposed the renderer it had just finished starting. It drew
  // exactly one frame and then sat there, empty, with no error anywhere.
  const [mounted, setMounted] = useState(false)
  const [live, setLive] = useState(false)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    // Reduced motion is a refusal, not a downgrade: this thing is a moving
    // light and there is no still version of it worth drawing.
    setMounted(!reduceMotion && typeof navigator !== 'undefined' && 'gpu' in navigator)
  }, [reduceMotion])

  useEffect(() => {
    if (!mounted) return
    const canvas = canvasRef.current
    const wordmark = wordmarkRef.current
    if (!canvas || !wordmark) return

    let cancelled = false
    let renderer
    // Imported here, not at module scope: vgpu is the single heaviest thing
    // this app can load (a 180 kB chunk), and a visitor without WebGPU must
    // never pay for it.
    import('../lib/flare/renderer')
      .then(({ createRenderer }) => {
        if (cancelled) return undefined
        renderer = createRenderer({ canvas, wordmark })
        return renderer.ready
      })
      .then(() => {
        if (!cancelled) setLive(true)
      })
      .catch((error) => {
        // An adapter that refuses, a driver that dies, a shader that will not
        // compile: all of it ends here, and the page keeps working.
        if (import.meta.env.DEV) console.warn('flare unavailable:', error)
        if (!cancelled) {
          setFailed(true)
          setLive(false)
        }
      })

    return () => {
      cancelled = true
      renderer?.dispose()
    }
  }, [mounted])

  const flare = failed || !mounted ? 'off' : live ? 'live' : 'pending'
  return { flare, flareCanvasRef: canvasRef, wordmarkRef }
}

function Home() {
  const [smilesText, setSmilesText] = useState('')
  const [examples, setExamples] = useState([])
  const [examplesError, setExamplesError] = useState(null)
  const [rows, setRows] = useState([])
  const [isSubmitting, setIsSubmitting] = useState(false)
  // Best-effort mode. Defaults ON, which is the behaviour Orthonym has always
  // shipped: a molecule the strict namer abstains on gets retried against
  // the escalated one. Turning it off makes the engine strict — it can then
  // only ever return a verified name or an honest abstain.
  const [bestEffort, setBestEffort] = useState(true)
  const [validationNote, setValidationNote] = useState(null)
  const [fetchError, setFetchError] = useState(null)
  const reduceMotion = useReducedMotion()
  const { flare, flareCanvasRef, wordmarkRef } = useWordmarkFlare(reduceMotion)

  // --- batch input ----------------------------------------------------
  // Two ways in, one card: paste for a handful, a file for the rest. The
  // paste box no longer refuses the eleventh line -- above the server's
  // fast-path limit it submits a background JOB instead, which is what the
  // server would have done anyway (POST /api/translate answers with an
  // envelope, not results, past that point).
  const [inputMode, setInputMode] = useState('paste')

  // The drawing editor, on the Draw tab only. `enabled` gates its 20 s
  // readiness clock: armed on page mount instead, anyone who picks Draw more
  // than 20 s after arriving finds an editor already declared broken, with no
  // iframe having ever existed to break. Same handshake /explain uses.
  const { iframeRef, editorState, handleFrameLoad, handleFrameError, getKetcher } = useKetcher({
    enabled: inputMode === 'draw',
  })
  const [file, setFile] = useState(null)
  const [preview, setPreview] = useState(null)
  const [dragging, setDragging] = useState(false)
  const [job, setJob] = useState(null)

  // A job still RUNNING in this browser is picked back up on load: its owner
  // token is in localStorage precisely so a reload does not lose the ability
  // to stop a 10,000-molecule job. A finished one is not -- BatchResults
  // forgets a job the moment it goes terminal, so reloading clears the page
  // instead of restoring a batch nothing could dismiss.
  useEffect(() => {
    const [mostRecent] = readJobs()
    if (mostRecent) setJob(mostRecent)
  }, [])

  const timersRef = useRef([])

  useEffect(() => {
    let cancelled = false
    fetchExamples()
      .then((data) => {
        if (!cancelled) setExamples(data)
      })
      .catch((err) => {
        if (!cancelled) setExamplesError(err?.message || 'network error')
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    return () => clearTimers()
  }, [])

  function clearTimers() {
    timersRef.current.forEach((id) => clearTimeout(id))
    timersRef.current = []
  }

  // Reveals settle per SMILES row (the batch "chase"), and within a row
  // ThreadedName animates per character. The direction's STORY promises
  // "rule-by-rule" reveal, but the /api/translate contract (see lib/api.js)
  // returns only a finished name per row, not its rule-firing/fragment
  // boundaries — Orthonym's name_tiered() doesn't expose that granularity
  // today. Per-character is the honest stand-in for "assembled piece by
  // piece" until a fragment-level API exists to reveal true rule order.
  function runTranslate(lines) {
    clearTimers()
    setFetchError(null)
    setRows(lines.map(emptyRow))
    setIsSubmitting(true)

    translateBatch(lines, { bestEffort })
      .then((results) => {
        setIsSubmitting(false)

        if (reduceMotion) {
          setRows(results.map((result) => ({ ...result, phase: 'done' })))
          return
        }

        let i = 0
        const revealNext = () => {
          if (i >= results.length) return
          const current = i
          setRows((prev) =>
            prev.map((row, idx) =>
              idx === current ? { ...results[current], phase: 'active' } : row,
            ),
          )
          const nameLength = results[current]?.name?.length ?? 0
          const chaseDuration = Math.min(1100, 380 + nameLength * 32)

          const settleTimer = setTimeout(() => {
            setRows((prev) =>
              prev.map((row, idx) => (idx === current ? { ...row, phase: 'done' } : row)),
            )
          }, chaseDuration)
          timersRef.current.push(settleTimer)

          i += 1
          const nextTimer = setTimeout(revealNext, chaseDuration + 90)
          timersRef.current.push(nextTimer)
        }
        revealNext()
      })
      .catch((err) => {
        setIsSubmitting(false)
        if (err instanceof TranslateJobQueuedError) {
          // Not a failure: the work is running on the server, it just did not
          // finish inside the fast-path timeout. This used to say "this page
          // cannot track a queued job's progress -- try a smaller batch",
          // which was true when there was no batch UI and became FALSE the
          // moment there was one. It hands the job to the batch panel now,
          // which is what the panel is for.
          const entry = {
            jobId: err.jobId,
            ownerToken: err.ownerToken,
            moleculeCount: err.moleculeCount,
          }
          rememberJob(entry)
          setJob(entry)
          setRows([])
          setValidationNote(
            `That took longer than the fast path allows, so it is running as a job you can ` +
              `watch, stop and download below.`
          )
          return
        }
        setFetchError(err?.message || 'unknown network error')
        setRows([])
      })
  }

  async function submitJob({ text = '', chosenFile = null, count = null }) {
    setIsSubmitting(true)
    setValidationNote(null)
    setFetchError(null)
    try {
      const envelope = await createJob({ file: chosenFile, text, bestEffort })
      // Remember it BEFORE anything else can fail: owner_token is returned
      // exactly once, and losing it means the job can never be stopped.
      const entry = {
        jobId: envelope.job_id,
        ownerToken: envelope.owner_token,
        moleculeCount: envelope.molecule_count ?? count,
      }
      rememberJob(entry)
      setJob(entry)
      setRows([])
    } catch (err) {
      // The server's own sentence is the useful one here: over the size cap,
      // no smiles column in the CSV, too many concurrent jobs.
      setValidationNote(err?.message || 'Could not start the job.')
    } finally {
      setIsSubmitting(false)
    }
  }

  async function submitDrawing() {
    const ketcher = getKetcher()
    if (!ketcher) {
      setValidationNote('The drawing area is still starting up. Give it a moment and try again.')
      return
    }
    let structure = ''
    try {
      structure = (await ketcher.getSmiles()) || ''
    } catch {
      setValidationNote('Could not read your drawing. Try drawing it again.')
      return
    }
    structure = structure.trim()
    if (!structure) {
      setValidationNote('Draw a molecule first, then press Translate.')
      return
    }
    // One molecule, so it takes the inline path and lands in the tiles beside
    // the editor -- no job, no progress bar.
    setValidationNote(null)
    setSmilesText(structure)
    runTranslate([structure])
  }

  function handleSubmit(event) {
    event.preventDefault()
    if (isSubmitting) return

    if (inputMode === 'draw') {
      void submitDrawing()
      return
    }

    if (inputMode === 'file') {
      if (!file) {
        setValidationNote('Choose a .sdf, .mol, .csv or .smi file first.')
        return
      }
      void submitJob({ chosenFile: file, count: preview?.molecule_count ?? null })
      return
    }

    const { lines, total } = parseSmilesLines(smilesText)
    if (!lines.length) {
      setValidationNote('Enter at least one SMILES string (one per line) before translating.')
      return
    }

    if (needsJob(total, MAX_ROWS)) {
      // Recomputed from the freshly parsed `total` rather than reading
      // `overFastPath`: the render-time count and the submit-time text are
      // the same in practice, and this keeps the decision next to the data
      // it was taken from.
      // The whole text goes up, not the truncated `lines`: the point of the
      // job path is that nothing gets dropped.
      void submitJob({ text: smilesText, count: total })
      return
    }

    setValidationNote(null)
    runTranslate(lines)
  }

  async function acceptFile(chosen) {
    setFile(chosen)
    setPreview(null)
    setValidationNote(null)
    if (!chosen) return
    try {
      setPreview(await parsePreview({ file: chosen, bestEffort }))
    } catch (err) {
      // A preview that fails is not a submission that fails; say so and let
      // them try anyway.
      setValidationNote(`Could not read that file: ${err?.message ?? 'unknown error'}`)
    }
  }

  function handleFilePick(event) {
    void acceptFile(event.target.files?.[0] ?? null)
  }

  // --- dropping a file on the card ------------------------------------
  // dragDepth counts enter/leave rather than tracking a boolean: dragging
  // over a child fires dragleave on the parent, so a boolean flickers the
  // armed state off and on as the pointer crosses the label inside the zone.
  const dragDepthRef = useRef(0)

  function endDrag() {
    dragDepthRef.current = 0
    setDragging(false)
  }

  function handleDragEnter(event) {
    if (isSubmitting) return
    // Only a file drag arms the zone -- dragging selected text over the card
    // is not an upload.
    if (!Array.from(event.dataTransfer?.types ?? []).includes('Files')) return
    event.preventDefault()
    dragDepthRef.current += 1
    setDragging(true)
  }

  function handleDragOver(event) {
    if (isSubmitting) return
    if (!Array.from(event.dataTransfer?.types ?? []).includes('Files')) return
    // Without preventDefault on dragover the browser keeps its own default
    // and the drop never reaches this handler at all.
    event.preventDefault()
    event.dataTransfer.dropEffect = 'copy'
  }

  function handleDragLeave() {
    if (dragDepthRef.current > 0) dragDepthRef.current -= 1
    if (dragDepthRef.current === 0) setDragging(false)
  }

  function handleDrop(event) {
    event.preventDefault()
    endDrag()
    if (isSubmitting) return
    const dropped = event.dataTransfer?.files
    if (!dropped || dropped.length === 0) return
    if (dropped.length > 1) {
      // One job, one file. Saying so beats silently naming the first of five.
      setValidationNote('One file at a time, please — that was ' + dropped.length + '.')
      return
    }
    const chosen = dropped[0]
    // Checked here rather than left to the server: a dropped file bypasses
    // the picker's `accept`, and "unsupported file type" is a better answer
    // than a 400 after a 50 MB upload.
    if (!ACCEPTED_FILE_RE.test(chosen.name)) {
      setValidationNote(
        `Orthonym reads .sdf, .mol, .csv, .smi and .txt — "${chosen.name}" is none of those.`
      )
      return
    }
    void acceptFile(chosen)
  }

  function startAnother() {
    if (job) forgetJob(job.jobId)
    setJob(null)
    setFile(null)
    setPreview(null)
    setValidationNote(null)
  }

  async function handleExamplePick(example) {
    if (isSubmitting) return

    // On the Draw tab an example DRAWS itself rather than naming itself.
    // Translating it there would answer a question the tab is not asking and
    // leave the canvas empty; loading it in means you can look at the
    // structure, edit it, and then press Translate -- which is the whole
    // point of picking an example while drawing.
    if (inputMode === 'draw') {
      const ketcher = getKetcher()
      if (!ketcher) {
        setValidationNote('The drawing area is still starting up. Give it a moment and try again.')
        return
      }
      try {
        await ketcher.setMolecule(example.smiles)
      } catch {
        setValidationNote('Could not load that structure into the editor.')
        return
      }
      setSmilesText(example.smiles)
      setValidationNote(null)
      return
    }

    setSmilesText(example.smiles)
    setValidationNote(null)
    runTranslate([example.smiles])
  }

  const hasResults = rows.length > 0
  // Counted from the same parser the submit path uses, so the hint and the
  // behaviour can never disagree.
  // Memoised on the text, not recomputed per render: every state change in
  // this page (typing, the flare going live, a poll landing) would otherwise
  // re-split and re-trim the whole textarea, which can hold up to the job
  // layer's 10,000-molecule cap.
  const pastedCount = useMemo(() => parseSmilesLines(smilesText).total, [smilesText])
  // ONE spelling of "this submission will not answer inline". It was written
  // three ways (needsJob() in the handler, `pastedCount > MAX_ROWS` in the
  // hint, and again in the button label), which agreed only because needsJob
  // happens to be that comparison today.
  const overFastPath = needsJob(pastedCount, MAX_ROWS)
  const willStartJob = inputMode === 'file' || overFastPath
  const submitLabel = isSubmitting ? 'Starting…' : willStartJob ? 'Start job' : 'Translate'

  return (
    <>
      {/* The hero. It carried a title and a four-line lede until 2026-09-02,
          when the owner replaced both with the wordmark and had the lede
          dropped outright (that copy still lives on About).
          The light is the real thing: vgpu's nextjs-flare (vercel-labs/vgpu,
          MIT), vendored into src/lib/flare and pointed at Orthonym's own
          wordmark -- a 48-step ray walk jittered by blue noise over a
          separable blur chain, raking light along the letter OUTLINES the way
          Next's "N" is lit. Not a glow in the middle of the card; the
          wordmark is the light source.
          It only runs where WebGPU exists and motion is welcome. Everywhere
          else the wordmark simply keeps its crimson text-shadow halo, which
          is why there is no canvas in the markup until we know. */}
      <section className="home-hero page-shell" aria-label="Introduction">
        {flare !== 'off' && (
          <canvas
            className="home-hero__flare"
            ref={flareCanvasRef}
            aria-hidden="true"
          />
        )}

        {/* When the flare is live it draws these letters itself, lit. The
            heading stays in the DOM at the same size -- it is what the flare
            is measured against, and what a screen reader and a crawler read
            -- but its ink goes transparent so the two do not double up. */}
        <h1
          className={
            flare === 'live' ? 'home-hero__word home-hero__word--lit' : 'home-hero__word'
          }
          ref={wordmarkRef}
        >
          Orthonym
        </h1>

        <p className="home-hero__tagline">Verified IUPAC names for Chemical Structures</p>
      </section>

      {/* ONE geometry per state, and the state is "is there anything to
          show", never "which tab is open".
          It used to flip to 8fr/4fr on the Draw tab so Ketcher got the wide
          cell. Measured, that made the input card resize on every tab
          switch -- 686x881 paste, 686x720 upload, 1372x1028 draw -- while
          sitting at the left of an almost empty second column. Now: one
          centred column until there are results, then an even split, and the
          field area holds a fixed height so the tabs cannot move anything. */}
      <main
        className={job || hasResults ? 'workbench workbench--split' : 'workbench'}
        aria-label="Translate SMILES to IUPAC names"
      >
        {fetchError && (
          <p className="workbench__alert" role="alert">
            Could not reach Orthonym&rsquo;s backend ({fetchError}). Is it running on{' '}
            <code>localhost:8000</code>?
          </p>
        )}

        <section className="workbench__input" aria-label="Translate a SMILES string">
          {/* Two ways in, one card. The tabs are radios rather than buttons
              so a keyboard gets arrow-key movement for free and the current
              choice is announced. */}
          <div className="input-tabs" role="radiogroup" aria-label="How to give Orthonym molecules">
            <label className={inputMode === 'paste' ? 'input-tab input-tab--on' : 'input-tab'}>
              <input
                type="radio"
                name="input-mode"
                value="paste"
                checked={inputMode === 'paste'}
                onChange={() => setInputMode('paste')}
                disabled={isSubmitting}
              />
              Paste
            </label>
            <label className={inputMode === 'file' ? 'input-tab input-tab--on' : 'input-tab'}>
              <input
                type="radio"
                name="input-mode"
                value="file"
                checked={inputMode === 'file'}
                onChange={() => setInputMode('file')}
                disabled={isSubmitting}
              />
              Upload file
            </label>
            <label className={inputMode === 'draw' ? 'input-tab input-tab--on' : 'input-tab'}>
              <input
                type="radio"
                name="input-mode"
                value="draw"
                checked={inputMode === 'draw'}
                onChange={() => setInputMode('draw')}
                disabled={isSubmitting}
              />
              Draw
            </label>
          </div>

          <form onSubmit={handleSubmit} noValidate>
            {inputMode === 'draw' ? (
              <div className="field">
                <span className="field__label">Draw a molecule</span>
                {editorState === 'error' ? (
                  <p className="workbench__note" role="alert">
                    The drawing area did not load. Reload the page to try again.
                  </p>
                ) : (
                  <iframe
                    ref={iframeRef}
                    title="Molecule drawing area"
                    className="structure-editor"
                    src="/standalone/index.html"
                    onLoad={handleFrameLoad}
                    onError={handleFrameError}
                  />
                )}
              </div>
            ) : inputMode === 'paste' ? (
              <div className="field">
                <label htmlFor="smiles-input" className="field__label">
                  SMILES &mdash; one per line
                </label>
                <textarea
                  id="smiles-input"
                  className="field__control"
                  /* 4, not 8: the field is flex: 1 inside a card that is
                     itself the flexible row of a one-screen page, so this is
                     a floor rather than a size -- it grows into whatever the
                     viewport leaves. */
                  rows={4}
                  spellCheck={false}
                  autoCorrect="off"
                  autoCapitalize="off"
                  placeholder={'CCO\nC[C@H](O)CC\nCC(C)(C)C1=CC2=C(C=C1)...'}
                  value={smilesText}
                  onChange={(event) => setSmilesText(event.target.value)}
                />
                {/* Only says anything once it MATTERS. The steady-state line
                    ("up to 10 answer here directly") cost 21px on every visit
                    to explain a rule nobody had hit yet, and the page has to
                    fit one screen. */}
                {overFastPath && (
                  <p className="field__hint">
                    {pastedCount} molecules — runs as a job you can watch, stop and download.
                  </p>
                )}
              </div>
            ) : (
              <div className="field">
                <span className="field__label" id="batch-file-label">
                  A file of molecules
                </span>
                {/* THE DROP ZONE. The whole area is the target, not a 90px
                    "Choose File" button in the corner of an empty card --
                    which is what this was, and a file manager's drag had
                    nowhere to land. The native input stays in the markup and
                    keeps doing the work: it is visually hidden rather than
                    replaced, so the keyboard, the label association and the
                    picker all behave exactly as the platform intends. */}
                <div
                  className={`dropzone${dragging ? ' dropzone--armed' : ''}${
                    file ? ' dropzone--loaded' : ''
                  }`}
                  onDragEnter={handleDragEnter}
                  onDragOver={handleDragOver}
                  onDragLeave={handleDragLeave}
                  onDrop={handleDrop}
                >
                  {/* The seam. A dashed rule is this system's mark for
                      "provisional" and the footer already sews one shut, so
                      an empty target is drawn as a seam waiting to be
                      sewn -- and while a file is over it, the dashes
                      actually run. SVG rather than a dashed border because a
                      border cannot animate its dashes, and one rect on the
                      GPU is cheaper than a repainting box-shadow. */}
                  <svg className="dropzone__seam" aria-hidden="true">
                    {/* 100% of an svg inset by 1px, NOT a rect inset by 1px:
                        width/height presentation attributes take a length or
                        a percentage and no calc(), and x/y/width/height as
                        CSS properties are not portable. The svg carries the
                        inset instead, and overflow: visible lets the stroke
                        straddle the path as strokes normally do. */}
                    <rect className="dropzone__seam-line" width="100%" height="100%" rx="13" />
                  </svg>

                  <input
                    id="batch-file"
                    className="dropzone__input"
                    type="file"
                    accept=".sdf,.mol,.csv,.smi,.txt"
                    onChange={handleFilePick}
                    disabled={isSubmitting}
                  />
                  <label htmlFor="batch-file" className="dropzone__face">
                    <span className="dropzone__mark" aria-hidden="true">
                      <span className="dropzone__mark-stroke" />
                      <span className="dropzone__mark-stroke" />
                      <span className="dropzone__mark-stroke" />
                    </span>
                    <span className="dropzone__lead">
                      {file ? file.name : 'Drop a file here'}
                    </span>
                    <span className="dropzone__sub">
                      {file ? 'Drop another to replace it' : 'or click to choose one'}
                    </span>
                    <span className="dropzone__formats">
                      <code>.sdf</code>
                      <code>.mol</code>
                      <code>.csv</code>
                      <code>.smi</code>
                      <code>.txt</code>
                    </span>
                    <span className="dropzone__note">
                      A <code>.csv</code> needs a <code>smiles</code> column; a plain list wants
                      one SMILES per line.
                    </span>
                  </label>
                </div>

                {preview && (
                  <div className="preview">
                    <p className="preview__count">
                      {preview.molecule_count} molecule
                      {preview.molecule_count === 1 ? '' : 's'} · read as{' '}
                      <code>{preview.format}</code>
                    </p>
                    {preview.errors.length > 0 && (
                      <ul className="preview__errors">
                        {preview.errors.map((message) => (
                          <li key={message}>{message}</li>
                        ))}
                      </ul>
                    )}
                    {/* This wording is deliberate and must not be softened to
                        "no errors found". The server parses only the first few
                        records, so a clean preview says nothing about row 6 --
                        ParsePreviewResponse's own docstring calls out that
                        this endpoint has never validated a whole file. */}
                    <p className="preview__caveat">
                      Checked the first {preview.sample.length} record
                      {preview.sample.length === 1 ? '' : 's'} only — later rows may still fail.
                    </p>
                  </div>
                )}
              </div>
            )}

            <Switch
              id="best-effort-mode"
              checked={bestEffort}
              onChange={setBestEffort}
              disabled={isSubmitting}
              label="Best-effort mode"
              onWord="On"
              offWord="Off"
              /* Short form. The three-line version cost 115px of a 631px
                 budget; this keeps the fact that decides whether to flip the
                 switch. The detail is on About, and an unverified RESULT now
                 names this switch itself (Tile.jsx). */
              hint={
                bestEffort
                  ? 'Unnameable molecules get a looser pass, always marked unverified.'
                  : 'Strict: only verified names, otherwise an honest abstain.'
              }
            />

            <div className="workbench__actions">
              <button type="submit" className="btn btn--accent" disabled={isSubmitting}>
                {submitLabel}
              </button>
              {job && (
                <button type="button" className="btn" onClick={startAnother}>
                  New batch
                </button>
              )}
              {validationNote && (
                <p className="workbench__note" role="status">
                  {validationNote}
                </p>
              )}
            </div>

            <ExampleChips
              examples={examples}
              error={examplesError}
              disabled={isSubmitting}
              onPick={handleExamplePick}
            />
          </form>

          {/* 46px for a sentence pointing at a page the header nav already
              links to, on a screen that has to hold everything. */}
        </section>

        {job ? (
          <BatchResults job={job} onForget={startAnother} />
        ) : hasResults ? (
          <SamplerGrid rows={rows} reduceMotion={reduceMotion} />
        ) : null /* Nothing at all until there is something to show. The key
                     moved to the band at the foot of the page, and the line
                     that replaced it ("submit a molecule and each result
                     appears here") cost 214px to describe the button
                     directly above it -- on a page that has to fit one
                     screen, that space belongs to the working area. */}
      </main>

      <ConfidenceLegend />

    </>
  )
}

export default Home
