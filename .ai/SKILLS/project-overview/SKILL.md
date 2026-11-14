---
name: project-overview
description: Current architecture, supported behavior, and important files for the wallpaper generator.
---

# Project overview

Gradient Wallpaper is a Python command-line program that creates procedural
desktop backgrounds. It is not a GUI application.

## Runtime and dependencies

- Python 3.10 or later.
- NumPy for seeded numerical image generation.
- Pillow for image filtering, resizing, and saving.
- Setuptools builds the installable package and console entry point.

## Main files

- `gradient_wallpaper/cli.py`: `create` and `eval` commands, argument parsing,
  randomization of omitted settings, validation, output, and seed reporting.
- `gradient_wallpaper/render.py`: palette classification, point-cloud
  gradients, wave masks, lighting, glue layer, halftone, grain, and optional
  progress callbacks. The CLI handles output encoding.
- `gradient_wallpaper/seed.py`: self-contained seed JSON serialization and
  validation.
- `gradient_wallpaper/__main__.py`: supports `python -m gradient_wallpaper`.
- `run.py` and `build.py`: entry point and one-command standalone packaging.
- `tests/`: standard-library `unittest` regression tests.
- `README.md`: installation, CLI, seed, and release instructions.

## User-facing behavior

- `gradient-wallpaper` defaults to `create`; `gradient-wallpaper create` is
  also supported. `gradient-wallpaper eval --seed VALUE` prints settings in a
  fixed order and resolves automatic wave choices.
- The default image size is 1920x1080.
- Colors accept `#RGB` and `#RRGGBB`; omitted palettes are generated in HSL.
- A self-contained seed stores colors and all render settings. Entropy-only
  text seeds deterministically generate omitted settings, which are included
  in the self-contained seed printed by `create`.
- Explicit numeric `random`/`unset` values draw fresh values on each run;
  the emitted self-contained seed records them for exact replay.
- Wave rotation and overscan zoom/offset are randomized from seed entropy when
  omitted, then stored for exact replay. Normalized random zoom stays close to
  0 (no zoom), or a 1x render scale.
- Wave opacity is a seeded visibility control; zero disables wave lighting and
  overlays. Random wave opacity stays close to full visibility.
- CLI wave amplitude and frequency use normalized `0`-`1` values, mapped to
  the renderer's existing physical ranges. Wave side uses orientation-relative
  `start`/`end` choices: top/bottom for horizontal waves and left/right for
  vertical waves.
- CLI glue spread is normalized from `0` to `1` and maps to the renderer's
  existing `0.1`-`0.8` size range.
- Random cloud spread has a 0.12 minimum to avoid isolated small color spots;
  explicit user settings retain the full supported spread range.
- CLI options override stored values when used with a self-contained seed.
- Interactive CLI runs display percentage progress on stderr; non-TTY runs
  omit the progress bar.
- Supported output formats are PNG, JPEG, and WebP.

## Working principles

Preserve reproducibility and current CLI behavior unless the task explicitly
changes them. Keep project guidance in sync with actual implementation; do not
copy historical design discussion into skills.
