---
name: rendering
description: Image-generation pipeline, color-space rules, effects, and deterministic random streams.
---

# Rendering conventions

The renderer lives in `gradient_wallpaper/render.py` and returns a Pillow RGB
image. Keep expensive pixel operations vectorized with NumPy and use Pillow
filters/resizing where already established.

## Pipeline

1. Classify palette roles and create a single wave mask plus lighting masks;
   apply the requested tilt to the path so lighting remains aligned. Apply
   wave opacity to the overlay, shadow/underglow, highlight, and chromatic
   effects consistently; zero opacity disables all wave contributions.
2. Generate two point-cloud gradients from the shared gradient palette.
3. Compose the background and wave using the existing screen/additive
   operation, then apply the selected seeded wave treatment.
4. Apply the Gaussian glue layer when enabled and when the palette has at least
   three unique colors.
5. Convert from linear light to sRGB; apply fine dither, ordered-dot halftone,
   and monochrome film grain before quantizing to 8-bit pixels. For zoom above
   0, render the full overscan canvas and crop to the requested output size
   without downscaling. Zoom is a 0–1 amount mapped to a 1–2x render scale.

Respect the current distinction between linear-light composition and sRGB
post-effects. Preserve requested output dimensions and RGB output after crop.
When randomizing `cloud_spread`, keep its minimum large enough to avoid
isolated colored point blobs; explicit user values may still use the full
supported range.

## Determinism

The render entry point is `render(...)`. It uses NumPy generators derived from
the seed for independent wave, mode, orientation, side, glue, halftone, and
grain choices. Keep unrelated effects on independent streams so changing one
effect does not needlessly reshuffle others.

`resolve_wave_options(...)` is the shared source of truth for automatic wave
mode, end style, orientation, and side. `eval` uses it to report the same
effective choices as rendering.

Validate direct renderer inputs and keep CLI ranges consistent with renderer
ranges. Add focused tests for new visual behavior, zero-strength no-ops,
repeatability, and edge cases.
