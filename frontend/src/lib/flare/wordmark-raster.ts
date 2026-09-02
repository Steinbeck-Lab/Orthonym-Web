// The flare's light source: the STITCH wordmark, drawn as OUTLINES.
//
// This file replaces upstream's logo-raster.ts, which held the Next.js "N" as
// an SVG string and rasterised it through an <img>. Two reasons it could not
// be adapted:
//
//   * The wordmark is text in a self-hosted webfont (Saira Condensed). An SVG
//     rendered through <img> cannot reach the page's fonts -- it would need
//     the whole face inlined as a data: URI, or the letters converted to
//     paths, and both drift the moment the type changes. Canvas 2D, by
//     contrast, can use a face the document has already loaded.
//   * The lit thing has to be the SAME wordmark the DOM shows, at the same
//     size and tracking, or the lit letters and the real letters do not line
//     up. So the metrics are read off the live element.
//
// Why STROKES and not fills: rim.wgsl lights a stroke and falls off with the
// square of the distance to the light, and the "N" it was built for is
// line art whose stroke gradient fades to nothing. A solid fill would light
// as one flat slab with no rake across it. Outlines give the light an edge to
// travel along, which is the whole effect.

const PAD = 3;

// Where the gradient along each stroke goes from lit to nothing. Upstream's
// SVG fades its two strokes with stops at offset 0.3 and 1.0; this is the
// same idea expressed diagonally across the whole word, so the light appears
// to rake from the top-left corner.
const GRADIENT_STOPS: ReadonlyArray<readonly [number, number]> = [
  [0, 1],
  [0.34, 0.92],
  [0.72, 0.34],
  [1, 0.06],
];

export interface WordmarkMetrics {
  readonly text: string;
  readonly family: string;
  readonly weight: string;
  /** Letter spacing as a fraction of the font size, so it survives scaling. */
  readonly trackingEm: number;
}

/** Reads what the live element is actually rendering, tracking included. */
export function wordmarkMetrics(element: HTMLElement): WordmarkMetrics {
  const style = getComputedStyle(element);
  const raw = (element.textContent ?? '').trim();
  const size = Number.parseFloat(style.fontSize) || 16;
  const spacing = Number.parseFloat(style.letterSpacing);
  return {
    text: style.textTransform === 'uppercase' ? raw.toUpperCase() : raw,
    family: style.fontFamily,
    weight: style.fontWeight,
    trackingEm: Number.isFinite(spacing) ? spacing / size : 0,
  };
}

/**
 * Strokes `metrics.text` into a transparent canvas of `width` x `height`
 * device pixels (plus a 3px guard band on every side, which logo.wgsl's
 * uvInset skips, exactly as upstream's rasteriser did).
 *
 * The font size is SOLVED rather than passed: a trial size is measured, then
 * scaled so the word fills the box on its tighter axis. That keeps this
 * correct when the hero, the viewport or the type scale changes, none of
 * which this file should have to know about.
 */
export async function rasterizeWordmark(
  metrics: WordmarkMetrics,
  width: number,
  height: number,
  signal?: AbortSignal
): Promise<HTMLCanvasElement> {
  const abortIfNeeded = () => {
    if (signal?.aborted) {
      throw new DOMException('Wordmark rasterization aborted.', 'AbortError');
    }
  };
  abortIfNeeded();

  // The display face is self-hosted and subsetted, so it can still be
  // pending on first paint. Measuring before it lands would size the word to
  // a fallback face and the lit letters would be the wrong width.
  await document.fonts?.ready;
  abortIfNeeded();

  const canvas = document.createElement('canvas');
  canvas.width = Math.max(1, Math.round(width)) + PAD * 2;
  canvas.height = Math.max(1, Math.round(height)) + PAD * 2;
  const context = canvas.getContext('2d');
  if (!context) throw new Error('Could not create the wordmark raster canvas.');

  const trial = 200;
  const measure = (size: number) => {
    context.font = `${metrics.weight} ${size}px ${metrics.family}`;
    const tracking = size * metrics.trackingEm;
    let advance = 0;
    let ascent = 0;
    let descent = 0;
    for (const character of metrics.text) {
      const box = context.measureText(character);
      advance += box.width + tracking;
      ascent = Math.max(ascent, box.actualBoundingBoxAscent || size * 0.72);
      descent = Math.max(descent, box.actualBoundingBoxDescent || 0);
    }
    // The trailing tracking is a gap after the last letter, not part of the
    // word -- the DOM wordmark pulls it back with a negative margin for the
    // same reason.
    return { advance: advance - tracking, ascent, descent, tracking };
  };

  const trialBox = measure(trial);
  const targetWidth = canvas.width - PAD * 2;
  const targetHeight = canvas.height - PAD * 2;
  const scale = Math.min(
    targetWidth / Math.max(trialBox.advance, 1),
    targetHeight / Math.max(trialBox.ascent + trialBox.descent, 1)
  );
  const size = Math.max(4, trial * scale);
  const box = measure(size);

  const originX = PAD + (targetWidth - box.advance) / 2;
  const baseline =
    PAD + (targetHeight - (box.ascent + box.descent)) / 2 + box.ascent;

  const gradient = context.createLinearGradient(
    PAD,
    PAD,
    PAD + targetWidth,
    PAD + targetHeight
  );
  for (const [offset, alpha] of GRADIENT_STOPS) {
    gradient.addColorStop(offset, `rgba(255, 255, 255, ${alpha})`);
  }

  context.strokeStyle = gradient;
  // Proportional to the type size, so the stroke keeps its weight at every
  // hero size instead of thinning out on a big display.
  // Thinner than it looks like it should be: a fat stroke gives the ray march
  // a wide, soft source and the rays come out as a smear. 0.010 of the type
  // size keeps the letters as lines.
  context.lineWidth = Math.max(1, size * 0.01);
  context.lineJoin = 'round';
  context.lineCap = 'round';
  context.textBaseline = 'alphabetic';

  // Drawn one character at a time rather than with ctx.letterSpacing, which
  // is not available in every engine that ships WebGPU. This also keeps the
  // advance identical to what was measured above.
  let cursor = originX;
  for (const character of metrics.text) {
    context.strokeText(character, cursor, baseline);
    cursor += context.measureText(character).width + box.tracking;
  }

  abortIfNeeded();
  return canvas;
}

export { PAD as WORDMARK_RASTER_PAD };
