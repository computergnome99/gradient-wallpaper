# Gradient Wallpaper

A small CLI for generating procedural desktop backgrounds. It classifies the
input palette into a primary background color, an optional wave accent, and
gradient colors. It creates two independently seeded point-cloud gradients,
then overlays one using a single blurred, end-faded grayscale wave mask. Point
colors blend in linear light and the layers use a screen/additive blend,
avoiding dark gaps between colors. Seeded dithering helps reduce visible color
banding. Optional post-effects add ordered, clustered-dot halftone dithering
and separate monochrome film grain. A final, faint layer of large Gaussian
color points softly blends across the wave and background; it is enabled when
the palette contains at least three unique colors.

## Install and run from source

Python 3.10 or later is required.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

This installs the `gradient-wallpaper` command and its NumPy/Pillow
dependencies in an isolated environment. From the project root, you can also
run it without installing the console script:

```sh
python -m gradient_wallpaper create --help
```

## Build a standalone executable

Build a one-file executable with one command:

```sh
python build.py
```

The script creates or reuses `.venv`, installs the build dependencies, and
places the executable in `dist/` (`gradient-wallpaper.exe` on Windows). No
environment activation or separate install/build steps are needed.

## Usage

```sh
gradient-wallpaper create --colors "#173b70" "#7165c8" "#f28a9b" "#ffb36b" \
  --seed sunset --output ~/Pictures/sunset.png
```

`create` is the default command, so the existing form without the word
`create` remains supported.

The default image is `1920x1080`; both dimensions can be set independently:

```sh
gradient-wallpaper --width 3840 --height 2160 \
  --colors "#071952" "#088395" "#35a29f" --seed 42
```

Provide any number of color stops (at least one). Colors accept `#RGB` and
`#RRGGBB` notation. The least saturated color is the primary in mixed-brightness
palettes; when most colors are bright or dark, the brightest or darkest color
is used instead. The seeded renderer chooses between a subtractive,
palette-colored shadow with directional highlight; an additive accent underglow
with a softer directional highlight; and, when at least four non-primary colors
are available, subtle chromatic fringes using the two brightest colors. With
fewer colors, aberration is omitted. Colors not reserved for the selected
effect form both point-cloud gradients, with different point placements and
orientations. With one or two stops, no accent is reserved and both stops
remain available to the gradients. `--color-order hue` sorts stops along the
shortest arc through HSV hue, useful for palettes that cross the red hue
boundary. With one stop, both layers use tonal variants of that color. Quote
`#`-prefixed colors in shells where `#` starts a comment.

When settings are provided, the CLI prints a self-contained seed containing
the colors, render settings, and procedural entropy used for the image. Save
that complete seed and pass it alone to reproduce the image:

```sh
gradient-wallpaper --seed '...' --output replay.png
```

Inspect the settings carried by a seed with `eval`:

```sh
gradient-wallpaper eval --seed '...'
gradient-wallpaper eval --seed sample-entropy
```

The report lists every setting in a fixed order. Self-contained seeds show
their stored values, resolving automatic wave options to the seeded choices.
Entropy-only seeds derive and show the same randomized settings that `create`
will use; dimensions show their defaults. The derived choices are repeatable
for the same seed.

If options are combined with a self-contained seed, explicitly supplied
settings override the stored values and a new seed is printed. Output path and
file format are not stored in the seed. Legacy text/numeric seeds are still
accepted as procedural entropy, randomize omitted visual settings from that
entropy, and are returned as self-contained seeds. Self-contained seeds have
no textual prefix; the CLI distinguishes them from entropy-only text seeds by
their encoded payload. Version-3 and version-4 self-contained seeds remain
readable. Version 3 receives neutral rotation, zoom, and offset settings; both
versions default the new opacity setting to full.

Without a self-contained seed, omitted visual settings are randomized and
baked into the printed seed. Random wave amplitude and frequency avoid near-flat
values: amplitude ranges from 0.06 to 0.18 and frequency from 1.5 to 4, both
biased toward their upper ends. Random cloud spread stays between 0.12 and 0.5
to avoid isolated small color spots. If colors are omitted, a random 3–6 color
HSL palette is created;
wave mode, orientation, end treatment, vertical foreground side, wave rotation,
zoom/offset, and glue-layer settings are chosen from the seed, along with
randomized halftone and grain strengths. Width and height remain `1920x1080`
unless specified. Random wave opacity stays between 0.92 and 1 and is biased
very heavily toward full opacity. Random rotation stays within ±15 degrees;
random zoom stays between 0 and 0.12 and is biased close to 0 (no zoom).
Optional controls:

```text
--wave-amplitude 0.22  Base wave amplitude (varied by seed), from 0 to 0.5
--wave-frequency 1    Base path detail (varied by seed), from 0 to 20
--wave-depth 0.75     Wave lighting and chromatic effect strength, from 0 to 1
--wave-opacity 1      Wave visibility, from 0 (off) to 1 (full)
--wave-mode auto      auto, shadow, underglow, or chromatic-aberration
--wave-ends auto      auto, fade, or edge-to-edge
--wave-orientation auto  auto, horizontal, or vertical
--wave-side auto      auto, left, or right foreground side for vertical waves
--wave-rotation 8     Wave tilt in degrees, from -15 to 15
--zoom 0              Overscale then crop, from 0 (off) to 1 (2x)
--offset-x 0          Horizontal offset in the overscan area, -1 to 1
--offset-y 0          Vertical offset in the overscan area, -1 to 1
--angle 20            Background point-cloud gradient direction
--dither 0.5          Dithering strength, from 0 (off) to 1
--cloud-spread 0.18   Gaussian point size/spread, from 0.03 to 0.5
--glue-points 2       Number of faint blending points, from 0 to 8 (0 disables)
--glue-colors 2       Number of colors used by the glue layer, 1 or 2
--glue-strength 0.07  Glue-layer opacity, from 0 to 0.25
--glue-spread 0.35    Glue-point size as a fraction of image dimensions
--halftone-strength 0.25  Ordered dot dithering, from 0 (off) to 1
--grain-strength 0.1      Film grain, from 0 (off) to 1
--color-order hue     Sort colors by hue instead of preserving input order
--format png          png, jpeg, or webp (otherwise inferred from the extension)
```

Choose `--wave-mode` to force a treatment; `auto` (the default) selects one
using a separate random stream derived from the seed. Forcing a mode does not
replace the seed, so the same seed and mode remain reproducible. Underglow
requires a suitable accent color, and chromatic aberration requires at least
four non-primary colors. Run `gradient-wallpaper create --help` for create
options or `gradient-wallpaper eval --help` for seed evaluation usage.

`--wave-ends` and `--wave-orientation` also accept `auto`, using separate
seed-derived choices, or can be explicitly set. `edge-to-edge` keeps the wave
at full strength where it meets the image boundaries; `fade` retains the
softened ends. Vertical orientation runs the wave from top to bottom instead
of left to right. Underglow is centered on the wave edge and follows its end
fade. Vertical waves choose a seeded left/right foreground side; set
`--wave-side left` or `--wave-side right` to force one (which also selects
vertical orientation when `--wave-orientation` is `auto`).
`--wave-opacity 0` disables the wave layer and all wave lighting/effects;
intermediate values fade the whole wave treatment. If omitted, opacity is
randomized very slightly and stays close to full visibility.
`--wave-rotation` tilts the wave and its lighting together, for either
orientation. `--zoom` ranges from `0` (no zoom) to `1` (2x zoom). It renders a
larger canvas and crops it back to the requested dimensions without scaling the
result down. The offset controls choose where the requested-size window sits
within the overscan: `0` centers it, while `-1` and `1` select the left/right
or top/bottom limit. Offsets have no visual effect when zoom is `0`.
The glue layer uses large, low-opacity Gaussian points to soften the boundary
between the two gradients without replacing either one. It is skipped for
palettes with fewer than three unique colors. Use `--glue-points 0` to disable
it, or adjust the number of points, palette colors, opacity, and spread. These
controls are included in versioned seeds.
`--halftone-strength` adds a clustered-dot screen that selects between nearby
brightness bands at a density determined by the gradient, making transitions
look more printed and less perfectly smooth. `--grain-strength` independently
adds fine monochrome grain over the finished image. Both effects are seeded,
can be disabled with `0`, and are included in self-contained seeds. The existing
`--dither` option remains a finer, low-amplitude noise dither.

PNG is the default output format. JPEG and WebP are supported by choosing a
matching output extension or using `--format`.

## GitHub releases

The GitHub Actions release workflow runs the tests and builds standalone
executables when a version tag such as `v0.1.0` is pushed. It publishes
Linux x86_64/ARM64, Windows x86_64, and macOS Intel/Apple Silicon assets to a
GitHub Release. These binaries are not code-signed or notarized, so Windows
SmartScreen or macOS Gatekeeper may show a security warning.

## Run tests

```sh
python -m unittest discover -s tests
```
