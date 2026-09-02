import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
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
  // Best-effort mode. Defaults ON, which is the behaviour STITCH has always
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
  const [job, setJob] = useState(null)

  // A job submitted from this browser is picked back up on load: its owner
  // token is in localStorage precisely so a reload does not lose the ability
  // to watch, stop or delete it. Expired entries prune themselves.
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
  // StitchedName animates per character. The direction's STORY promises
  // "rule-by-rule" reveal, but the /api/translate contract (see lib/api.js)
  // returns only a finished name per row, not its rule-firing/fragment
  // boundaries — OpenSTOUT's name_tiered() doesn't expose that granularity
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

  async function handleFilePick(event) {
    const chosen = event.target.files?.[0] ?? null
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

  function startAnother() {
    if (job) forgetJob(job.jobId)
    setJob(null)
    setFile(null)
    setPreview(null)
    setValidationNote(null)
  }

  function handleExamplePick(example) {
    if (isSubmitting) return
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
          MIT), vendored into src/lib/flare and pointed at STITCH's own
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
          Stitch
        </h1>

        {/* The bold letters spell STITCH: S-T-I-T-C-H. "Ch" keeps the word's
            real spelling rather than shouting CH to force the acronym --
            the pattern still reads. Each one glows crimson under the
            pointer, which is the whole reason they are marked at all. */}
        <p className="home-hero__tagline">
          <b className="home-hero__cap">S</b>MILES <b className="home-hero__cap">T</b>o{' '}
          <b className="home-hero__cap">I</b>UPAC name{' '}
          <b className="home-hero__cap">T</b>ranslator for{' '}
          <b className="home-hero__cap">Ch</b>emistry
        </p>
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
            Could not reach STITCH&rsquo;s backend ({fetchError}). Is it running on{' '}
            <code>localhost:8000</code>?
          </p>
        )}

        <section className="workbench__input" aria-label="Translate a SMILES string">
          {/* Two ways in, one card. The tabs are radios rather than buttons
              so a keyboard gets arrow-key movement for free and the current
              choice is announced. */}
          <div className="input-tabs" role="radiogroup" aria-label="How to give STITCH molecules">
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
                  rows={8}
                  spellCheck={false}
                  autoCorrect="off"
                  autoCapitalize="off"
                  placeholder={'CCO\nC[C@H](O)CC\nCC(C)(C)C1=CC2=C(C=C1)...'}
                  value={smilesText}
                  onChange={(event) => setSmilesText(event.target.value)}
                />
                {/* Says what will happen before it happens: up to ten come
                    back here, more than ten run as a job with a progress bar. */}
                <p className="field__hint">
                  {overFastPath
                    ? `${pastedCount} molecules — runs as a background job you can watch, stop and download.`
                    : `Up to ${MAX_ROWS} answer here directly. Paste more and STITCH runs them as a job.`}
                </p>
              </div>
            ) : (
              <div className="field">
                <label htmlFor="batch-file" className="field__label">
                  A file of molecules
                </label>
                <input
                  id="batch-file"
                  className="field__file"
                  type="file"
                  accept=".sdf,.mol,.csv,.smi,.txt"
                  onChange={handleFilePick}
                  disabled={isSubmitting}
                />
                <p className="field__hint">
                  <code>.sdf</code>, <code>.mol</code>, <code>.csv</code> (needs a{' '}
                  <code>smiles</code> column) or one SMILES per line.
                </p>

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
              hint={
                bestEffort
                  ? 'A molecule the strict rules cannot name is retried with a looser pass. That can return a real name OPSIN could not confirm — always marked as unverified, never as a PIN.'
                  : 'Strict. Only names the engine can verify are shown; anything else comes back as an honest abstain rather than an unverified guess.'
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

          <p className="page-about-note workbench__about">
            Read how this works, and STITCH&rsquo;s measured accuracy, on the{' '}
            <Link to="/about" className="about-link">
              About
            </Link>{' '}
            page.
          </p>
        </section>

        {job ? (
          <BatchResults job={job} onForget={startAnother} />
        ) : hasResults ? (
          <SamplerGrid rows={rows} reduceMotion={reduceMotion} />
        ) : (
          /* The key used to live here, which meant it vanished the moment
             there were results to read it against. It is a band at the foot
             of the page now, so this cell only has to say what will happen. */
          <p className="workbench__empty">
            {inputMode === 'draw'
              ? 'Draw a molecule, press Translate, and its name appears here with the mark that earned it.'
              : 'Submit a molecule and each result appears here, carrying its own mark.'}
          </p>
        )}
      </main>

      <ConfidenceLegend />

    </>
  )
}

export default Home
