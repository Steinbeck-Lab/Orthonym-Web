struct Params {
  light: vec2f,
  aspect: vec2f,
  logoCenter: vec2f,
  flareColor: vec3f,
  rimIntensity: f32,
  extension: f32,
  beamIntensity: f32,
  filmGrain: f32,
  smoothness: f32,
  logoOpacity: f32,
  frameIndex: u32,
  spotFocus: f32,
  scatter: f32,
  rimFill: f32,
  verticalEdgeFade: f32,
}
@group(0) @binding(0) var linearSampler: sampler;
@group(0) @binding(1) var sceneTexture: texture_2d<f32>;
@group(0) @binding(2) var rimTexture: texture_2d<f32>;
@group(0) @binding(3) var rimBlurTexture: texture_2d<f32>;
@group(0) @binding(4) var blueNoiseTexture: texture_2d<f32>;
@group(0) @binding(5) var<uniform> params: Params;

fn resolveDarkColor(radiance: vec3f) -> vec3f {
  return max(vec3f(0.0), vec3f(1.0) - exp(-radiance * 1.3));
}

@fragment fn fs_main(@location(0) uv: vec2f) -> @location(0) vec4f {
  let scene = textureSample(sceneTexture, linearSampler, uv).r;
  let rimSample = textureSample(rimTexture, linearSampler, uv).r;
  let rimBlur = textureSample(rimBlurTexture, linearSampler, uv).r;
  let direction = uv - params.light;
  let decay = mix(0.85, 0.975, params.extension);
  let density = mix(0.35, 1.15, params.extension);
  let delta = direction * (density / 48.0);
  let dimensions = textureDimensions(rimTexture);
  let pixel = vec2u(clamp(uv * vec2f(dimensions), vec2f(0.0), vec2f(dimensions) - vec2f(1.0)));
  let offset = vec2u(params.frameIndex * 73u, params.frameIndex * 23u);
  let noisePixel = (pixel + offset) & vec2u(127u);
  let blueNoise = textureLoad(blueNoiseTexture, vec2i(noisePixel), 0).r;
  let jitter = fract(blueNoise + f32(params.frameIndex) * 0.61803398875);
  var coordinate = uv - delta * jitter * params.smoothness;
  var illumination = 1.0;
  var illuminationSum = 0.0;
  var rimRays = 0.0;
  for (var i = 0; i < 48; i++) {
    coordinate -= delta;
    let sharpRay = textureSample(rimTexture, linearSampler, coordinate).r;
    let blurredRay = textureSample(rimBlurTexture, linearSampler, coordinate).r;
    rimRays += mix(sharpRay, blurredRay, params.smoothness) * illumination;
    illuminationSum += illumination;
    illumination *= decay;
  }
  // Preserve the extension=1 energy while allowing extension to control reach.
  rimRays = rimRays / max(illuminationSum, 0.001) * 4.102966;

  let haloDelta = (uv - params.light) * params.aspect;
  let haloRadius = mix(0.05, 0.6, params.spotFocus);
  let halo = exp(-dot(haloDelta, haloDelta) / (haloRadius * haloRadius));
  let lineCoverage = max(scene, rimBlur * 0.65);
  // VENDORED CHANGE: 1.1 -> 0.45. The halo is the part that becomes a blob
  // on a light ground; the rays are the part worth seeing.
  let haloLine = halo * lineCoverage * params.rimIntensity * 0.45;
  let spot = max(rimSample, rimBlur * 0.85 * params.rimFill) * (1.0 + halo * 1.5);
  let scatterSignal = rimRays * params.beamIntensity * params.scatter;

  var radiance = params.flareColor * haloLine;
  // VENDORED CHANGE: dropped. Upstream paints the letter bodies here, which
  // is right when the canvas IS the logo. Here the DOM <h1> is the logo --
  // real text, real font, selectable, readable by a screen reader -- and this
  // term only fought it: premultiplied over grey it came out as a second,
  // darker set of letters offset behind the real ones. The canvas's job is
  // the LIGHT: rim glow and rays. Not the letterforms.
  // radiance += vec3f(scene) * params.logoOpacity * 0.22;
  // VENDORED CHANGE: 0.5 -> 0.85. Upstream can afford a half-white spot
  // because it sits on black. On grey, white light disappears -- the flare
  // has to stay crimson to read at all.
  // VENDORED CHANGE: 0.5 -> 0.85 colour (white light is invisible on grey),
  // and the spot's own weight halved -- it is the term that sat on top of the
  // letters.
  radiance += mix(vec3f(1.0), params.flareColor, 0.85) * spot * params.rimIntensity * 0.5;
  radiance += params.flareColor * spot * 0.22 * params.rimIntensity;
  // VENDORED CHANGE: the rays carry 1.7x. See haloLine above -- this is the
  // other half of that trade.
  radiance += params.flareColor * scatterSignal * 1.7;

  let radialMask = smoothstep(1.35, 0.25, length((uv - params.logoCenter) * params.aspect));
  let color = resolveDarkColor(radiance * radialMask);
  let beamSignal = scatterSignal * radialMask;
  let verticalFadeWidth = max(params.verticalEdgeFade, 0.0001);
  let horizontalFadeWidth = verticalFadeWidth * params.aspect.y / max(params.aspect.x, 0.0001);
  let verticalEdgeMask = smoothstep(0.0, verticalFadeWidth, uv.y) * smoothstep(0.0, verticalFadeWidth, 1.0 - uv.y);
  let horizontalEdgeMask = smoothstep(0.0, horizontalFadeWidth, uv.x) *
    smoothstep(0.0, horizontalFadeWidth, 1.0 - uv.x);
  let edgeMask = verticalEdgeMask * horizontalEdgeMask;
  let composed = mix(vec3f(0.0), color, edgeMask);

  // A decorrelated blue-noise layer masks sparse ray-march structure only in
  // dim and mid scattering, leaving the logo and flat background untouched.
  let grainOffset = vec2u(params.frameIndex * 37u + 53u, params.frameIndex * 109u + 17u);
  let grainPixel = (pixel * vec2u(3u, 5u) + grainOffset) & vec2u(127u);
  let grainSample = textureLoad(blueNoiseTexture, vec2i(grainPixel), 0).r;
  let grain = (fract(grainSample + f32(params.frameIndex) * 0.61803398875 + 0.38196601125) - 0.5) * 2.0;
  let beamGate = smoothstep(0.003, 0.05, beamSignal) * (1.0 - smoothstep(0.4, 1.0, beamSignal));
  let logoCoverage = max(scene, max(rimSample, rimBlur));
  let grainMask = beamGate * (1.0 - smoothstep(0.02, 0.3, logoCoverage)) * edgeMask;
  let grained = clamp(composed + vec3f(grain * params.filmGrain * grainMask), vec3f(0.0), vec3f(1.0));
  // VENDORED CHANGE, and the most important one in this fork. Upstream ends
  // with vec4f(grained, 1.0): light ADDED to a black page, which is the only
  // way a flare can work on black.
  //
  // Orthonym's hero is on a light grey ground, and light-on-light is invisible
  // -- measured, not assumed: with the frame emitted as premultiplied light
  // the rays vanished completely and only the halo around the letters showed.
  // So the frame is INVERTED here into a crimson veil and the canvas is
  // composited with mix-blend-mode: multiply. Where the shader put no light
  // the veil is white, and white multiplied over the ground is the ground
  // untouched. Where it put light, the veil tends toward the flare colour and
  // darkens the paper along exactly the same rays.
  //
  // This is light behaving like ink, which is the honest reading of a light
  // leak on paper -- and it is the only version in which the ray structure
  // upstream computes is actually visible here.
  // The one knob for "how much flare". 1.05 read as too much on the page, so
  // it is halved: the ray structure is unchanged, the veil it lays on the
  // paper is half as dense.
  let lit = clamp(max(grained.r, max(grained.g, grained.b)) * 0.52, 0.0, 1.0);
  let veil = mix(vec3f(1.0), params.flareColor, lit);
  let grainedVeil = clamp(
    veil - vec3f(grain * params.filmGrain * grainMask),
    vec3f(0.0),
    vec3f(1.0)
  );
  return vec4f(grainedVeil, 1.0);
}
