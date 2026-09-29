import { init, surface, type Gpu } from "vgpu";

import { rasterizeWordmark, wordmarkMetrics } from "./wordmark-raster";
import {
  backingDimensions,
  canvasRaster,
  FlarePipeline,
  followLight,
  LOGO_CENTER,
  runCleanups,
  type FlarePlacement,
  type Point,
} from "./pipeline";

// VENDORED from vgpu's nextjs-flare example (vercel-labs/vgpu, MIT) and
// changed in four places, each marked "VENDORED CHANGE" here or in the file
// it touches:
//   1. The light source is Orthonym's wordmark, measured off the live <h1> and
//      stroked into a canvas, instead of the Next.js "N" SVG.
//   2. The placement is that <h1>'s own rectangle, so the lit letters land on
//      the real ones rather than in the middle of a square.
//   3. composite.wgsl emits a crimson veil that the canvas multiplies onto
//      the grey page ground, and the surface is premultiplied so an undrawn
//      canvas is clear instead of a black frame.
//   4. The flare colour is --accent crimson, not Next's blue-white.
// Everything else -- the 48-step ray walk, the blue-noise jitter, the
// separable blur chain, the pointer light, the resize choreography -- is
// theirs and should be left alone.

type RenderSize = Readonly<{ width: number; height: number; dpr: number }>;

// VENDORED CHANGE: 33 -> 10. Upstream throttles to ~30fps; the owner asked
// for "super smooth", so 10ms keeps every frame up to ~100Hz and every other
// frame above it (72fps at 144Hz) rather than a full march per refresh.
const FRAME_INTERVAL_MS = 10;
const PULSE_HOLD_SECONDS = 0.35;

/**
 * Where the light drifts when nobody is pointing at it.
 *
 * Replaces upstream's mapAutonomousLight, which orbits a square derived from
 * min(canvasWidth, canvasHeight) -- on a hero five times wider than it is
 * tall that swings the light off the band entirely and leaves the letters
 * unlit for most of the cycle. This orbits the WORDMARK: a wide, slow ellipse
 * that runs along the word and rises just past its cap height, so the rake
 * travels letter to letter the way it travels down the "N" upstream.
 */
function wordmarkOrbit(timeSeconds: number, placement: FlarePlacement): Point {
  const phase = timeSeconds * 0.3;
  const spanX = placement.logoScale[0] * 0.72;
  const spanY = placement.logoScale[1] * 0.62;
  return [
    placement.logoCenter[0] + Math.cos(phase) * spanX,
    placement.logoCenter[1] + Math.sin(phase * 0.83) * spanY,
  ];
}

export function createRenderer({
  canvas,
  wordmark,
  onFail,
}: {
  readonly canvas: HTMLCanvasElement;
  /** The live <h1>. Its text, face, tracking and rectangle drive the flare. */
  readonly wordmark: HTMLElement;
  /**
   * Called once when the renderer fails, at start-up or later -- a lost GPU
   * device (Android drops it when the app goes to the background), a draw or a
   * resize that throws. `ready` settles once, so it cannot report the later ones.
   */
  readonly onFail?: (error: unknown) => void;
}) {
  let disposed = false;
  let failed = false;
  let gpu: Gpu | undefined;
  let pipeline: FlarePipeline | undefined;
  let placement: FlarePlacement | undefined;
  let light: Point = LOGO_CENTER;
  let pointer: Point | undefined;
  let pulseHold = 0;
  let frameIndex = 0;
  let staticDirty = true;
  let lastTime = 0;
  let lastRender = -Infinity;
  let animationFrame = 0;
  let observer: ResizeObserver | undefined;
  let pendingSize: RenderSize | undefined;
  let resizeTask: Promise<void> | undefined;
  let resizeGeneration = 0;
  let rasterAbort: AbortController | undefined;
  let appliedBacking: Point = [0, 0];
  let appliedSupersample = 0;

  const applySize = async (size: RenderSize, generation: number) => {
    if (!pipeline) return;
    const backing = backingDimensions(size.width, size.height, size.dpr);
    const supersample = size.dpr < 1.5 ? 2 : 1;
    if (
      backing[0] === appliedBacking[0] &&
      backing[1] === appliedBacking[1] &&
      supersample === appliedSupersample
    ) {
      return;
    }

    const controller = new AbortController();
    rasterAbort = controller;

    // VENDORED CHANGE: the logo box is the live wordmark's rectangle mapped
    // into the canvas, not a fraction of min(width, height). Backing pixels
    // per CSS pixel comes from the canvas's own rect so this stays right at
    // any devicePixelRatio, and at the supersample the renderer picked.
    const canvasRect = canvas.getBoundingClientRect();
    const wordRect = wordmark.getBoundingClientRect();
    const perCssX = backing[0] / Math.max(canvasRect.width, 1);
    const perCssY = backing[1] / Math.max(canvasRect.height, 1);
    const boxWidth = Math.max(1, Math.round(wordRect.width * perCssX));
    const boxHeight = Math.max(1, Math.round(wordRect.height * perCssY));
    const centreX =
      (wordRect.left - canvasRect.left + wordRect.width / 2) *
      perCssX /
      Math.max(backing[0], 1);
    const centreY =
      (wordRect.top - canvasRect.top + wordRect.height / 2) *
      perCssY /
      Math.max(backing[1], 1);

    let logo: HTMLCanvasElement;
    try {
      logo = await rasterizeWordmark(
        wordmarkMetrics(wordmark),
        boxWidth * supersample,
        boxHeight * supersample,
        controller.signal
      );
    } catch (error) {
      if (controller.signal.aborted) return;
      throw error;
    } finally {
      if (rasterAbort === controller) rasterAbort = undefined;
    }
    if (disposed || generation !== resizeGeneration) return;

    const reference = Math.max(1, Math.min(backing[0], backing[1]));
    const requested: FlarePlacement = {
      logoCenter: [centreX, centreY],
      logoScale: [boxWidth / backing[0], boxHeight / backing[1]],
      // This is upstream's value and it has to stay upstream's value: rim.wgsl
      // and composite.wgsl use it as the ASPECT that makes a distance in UV
      // space isotropic. An earlier version put the canvas-to-wordmark ratio
      // here instead, on the theory that it only drove the light orbit -- the
      // halo came out as a wide horizontal ellipse smeared across the hero,
      // because every distance was being measured in the wrong units. The
      // light orbit is handled separately, below.
      canvasToLogo: [backing[0] / reference, backing[1] / reference],
    };

    const nextPlacement = await pipeline.replace(
      backing,
      supersample,
      canvasRaster(logo),
      () => disposed || generation !== resizeGeneration,
      requested
    );
    if (!nextPlacement) return;
    placement = nextPlacement;
    appliedBacking = backing;
    appliedSupersample = supersample;
    staticDirty = true;
  };

  const drainResizes = async () => {
    while (pendingSize && !disposed) {
      const size = pendingSize;
      pendingSize = undefined;
      await applySize(size, resizeGeneration);
    }
  };

  const resize = (size: RenderSize): Promise<void> => {
    if (disposed || size.width <= 0 || size.height <= 0)
      return Promise.resolve();
    pendingSize = size;
    resizeGeneration += 1;
    rasterAbort?.abort();
    resizeTask ??= drainResizes()
      .catch((error: unknown) => {
        if (disposed && !failed) return;
        fail(error);
      })
      .finally(() => {
        resizeTask = undefined;
      });
    return resizeTask;
  };

  const measure = () =>
    guard(() => {
      const rect = canvas.getBoundingClientRect();
      resize({
        width: rect.width,
        height: rect.height,
        dpr: window.devicePixelRatio || 1,
      }).catch(() => {
        // fail() has already reported it through onFail.
      });
    });

  const handlePointerMove = (event: PointerEvent) => {
    if (event.pointerType === "touch") return;
    guard(() => {
      const rect = canvas.getBoundingClientRect();
      const x = Math.min(
        1,
        Math.max(0, (event.clientX - rect.left) / Math.max(1, rect.width))
      );
      const y = Math.min(
        1,
        Math.max(0, (event.clientY - rect.top) / Math.max(1, rect.height))
      );
      // VENDORED CHANGE: the light is held near the wordmark.
      //
      // Upstream hands the raw pointer straight through, which is right for a
      // logo that fills a tall panel. Here the hero is a wide, short band and
      // the letters occupy a strip through the middle of it: with the pointer
      // free, moving it to the tagline put the light well below the strokes,
      // rim.wgsl's inverse-square falloff took over, and the whole effect
      // switched off -- measured, the hero went flat grey. Clamped to a
      // generous box around the letters, the light still tracks the pointer
      // (that is the one interaction this thing has) but can never leave the
      // word dark.
      if (!placement) {
        pointer = [x, y];
        return;
      }
      const reachX = (placement.logoScale[0] / 2) * 1.7;
      const reachY = (placement.logoScale[1] / 2) * 1.5;
      pointer = [
        Math.min(
          placement.logoCenter[0] + reachX,
          Math.max(placement.logoCenter[0] - reachX, x)
        ),
        Math.min(
          placement.logoCenter[1] + reachY,
          Math.max(placement.logoCenter[1] - reachY, y)
        ),
      ];
    });
  };

  const handlePointerLeave = () => {
    pointer = undefined;
  };

  const frameLoop = (now: number) => {
    if (disposed) return;
    guard(() => {
      animationFrame = requestAnimationFrame(frameLoop);
      const activePipeline = pipeline;
      if (now - lastRender < FRAME_INTERVAL_MS || !placement || !activePipeline)
        return;
      lastRender = now;
      const time = now / 1000;
      const dt = Math.min(Math.max(time - lastTime, 0), 0.05);
      lastTime = time;
      const target = pointer ?? wordmarkOrbit(time, placement);
      light = followLight(light, target, dt);
      pulseHold +=
        ((pointer ? 1 : 0) - pulseHold) *
        (1 - Math.exp(-dt / PULSE_HOLD_SECONDS));
      activePipeline.setFrameUniforms(
        placement,
        light,
        frameIndex,
        time,
        pulseHold
      );
      activePipeline.draw(staticDirty);
      staticDirty = false;
      frameIndex += 1;
    });
  };

  const dispose = () => {
    if (disposed) return;
    disposed = true;
    resizeGeneration += 1;
    runCleanups([
      () => rasterAbort?.abort(),
      () => {
        if (animationFrame) cancelAnimationFrame(animationFrame);
      },
      () => observer?.disconnect(),
      () => canvas.removeEventListener("pointermove", handlePointerMove),
      () => canvas.removeEventListener("pointerleave", handlePointerLeave),
      () => canvas.removeEventListener("pointercancel", handlePointerLeave),
      () => gpu?.dispose(),
    ]);
  };

  function report(error: unknown): void {
    if (failed) return;
    failed = true;
    try {
      dispose();
    } catch {
      // Teardown must not replace the live or initialization failure.
    }
    onFail?.(error);
  }

  // For the promise chains that must still reject (`ready`, a resize).
  function fail(error: unknown): never {
    report(error);
    throw error;
  }

  // For event callbacks (frames, resizes, the pointer): rethrowing into the
  // browser would only leave an uncaught error behind.
  function guard(work: () => void): void {
    try {
      work();
    } catch (error) {
      report(error);
    }
  }

  const initialize = async () => {
    // VENDORED CHANGE: upstream imported vgpu dynamically here. This whole
    // module is already behind a dynamic import in Home.jsx -- and pipeline.ts
    // imports vgpu statically anyway, so the inner import bought nothing and
    // only made the bundler warn. The split that matters still holds: vgpu
    // lands in the renderer chunk (180 kB), which a visitor without WebGPU
    // never fetches.
    if (disposed) return;
    const nextGpu = await init({ label: "orthonym-wordmark-flare" });
    if (disposed) {
      try {
        nextGpu.dispose();
      } catch {
        // Intentional stale initialization is quiet.
      }
      return;
    }
    gpu = nextGpu;
    const output = surface(gpu, canvas, {
      autoResize: false,
      // The shader writes alpha 1, so a drawn frame is the same in either mode,
      // but "opaque" shows an undrawn canvas (before the first frame, after a
      // resize clears it) as black, and multiplied that is a black box over the
      // wordmark -- visible on a tablet GPU slow to compile the shaders.
      alphaMode: "premultiplied",
      format: "bgra8unorm",
    });
    pipeline = new FlarePipeline(gpu, output);
    const rect = canvas.getBoundingClientRect();
    await resize({
      width: Math.max(1, rect.width),
      height: Math.max(1, rect.height),
      dpr: window.devicePixelRatio || 1,
    });
    if (disposed) return;
    light = placement?.logoCenter ?? LOGO_CENTER;
    canvas.addEventListener("pointermove", handlePointerMove);
    canvas.addEventListener("pointerleave", handlePointerLeave);
    canvas.addEventListener("pointercancel", handlePointerLeave);
    observer =
      typeof ResizeObserver === "undefined"
        ? undefined
        : new ResizeObserver(measure);
    observer?.observe(canvas);
    animationFrame = requestAnimationFrame(frameLoop);
  };

  const ready = initialize().catch((error: unknown) => {
    if (disposed && !failed) return;
    fail(error);
  });

  return { ready, resize, dispose };
}
