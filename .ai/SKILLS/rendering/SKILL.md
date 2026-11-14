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
   wave opacity and edge strength to the overlay and all selected edge
   treatments consistently; zero opacity disables all wave contributions.
   Compress shadow strength toward its high end so darkening does not overwhelm
   the underlying gradient.
2. Generate two point-cloud gradients from the shared gradient palette.
3. Compose the background and wave using the existing screen/additive
   operation, then apply the selected seeded wave-edge treatment. Aberration
   uses additive red, green, and blue fringes whose saturation and lightness
   are the arithmetic means of the input palette's HSL values. It is supported
   for any palette size, does not reserve palette colors, and increases fringe
   separation slightly with edge strength.
   Underglow is a broad, one-sided additive accent on the background side of
   the edge; preserve the same wave gradient and highlight used by shadow mode.
4. Apply the Gaussian glue layer when enabled. Each point uses a seeded
   linear-light mixture of all unique palette colors.
5. Convert from linear light to sRGB; apply fine dither, ordered-dot halftone,
   and monochrome film grain before quantizing to 8-bit pixels. For zoom above
   0, render the full overscan canvas and crop to the requested output size
   without downscaling. Zoom is a 0–1 amount mapped to a 1–2x render scale.

Respect the current distinction between linear-light composition and sRGB
post-effects. Preserve requested output dimensions and RGB output after crop.
`cloud_spread` is a normalized 0–1 setting mapped to an internal 0.03–0.5
fractional size. `glue_strength` is normalized to 0–1 and mapped to an internal
maximum opacity of 0.25. When randomizing cloud spread, keep its effective
minimum large enough to avoid isolated colored point blobs.

The optional `render(..., progress_callback=...)` reports monotonic integer
percentages and phase labels. Keep callback reports tied to actual pipeline
work; the CLI renders them as a terminal-only progress bar on stderr.

## Determinism

The render entry point is `render(...)`. It uses NumPy generators derived from
the seed for independent wave, mode, orientation, side, glue, halftone, and
grain choices. Keep unrelated effects on independent streams so changing one
effect does not needlessly reshuffle others.

`resolve_wave_options(...)` is the shared source of truth for automatic
wave-edge treatment, end style, orientation, and side. `eval` uses it to report the same
effective choices as rendering.

Validate direct renderer inputs and keep CLI ranges consistent with renderer
ranges. Add focused tests for new visual behavior, zero-strength no-ops,
repeatability, and edge cases.
