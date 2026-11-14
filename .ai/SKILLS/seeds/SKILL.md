---
name: seeds
description: Seed payload structure, entropy handling, replay guarantees, and evaluation output.
---

# Seeds and reproducibility

Seed logic is in `gradient_wallpaper/seed.py`; creation and evaluation are
coordinated by `gradient_wallpaper/cli.py`.

- A current self-contained seed is unpadded URL-safe Base64 JSON with an
  internal integer `version` (currently 11), an `entropy` string, and a complete
  `settings` object. There is no textual prefix.
- `SeedSettings` is the authoritative set of persisted rendering fields.
  Update it whenever a new rendering setting is introduced.
- `encode_seed` and `decode_seed` must remain inverses for valid current
  payloads. Validate exact setting keys and value types when decoding.
- A non-self-contained input is treated as entropy text. `create` derives
  omitted visual settings deterministically from it, then prints a
  self-contained seed that can replay the result.
- Explicit numeric `random`/`unset` options are an exception to omitted-setting
  determinism: they draw fresh values per invocation, and the emitted seed
  stores those chosen values for exact replay.
- When a self-contained seed is combined with explicit options, apply those
  options over the stored settings and emit a new self-contained seed.
- Numeric visual CLI options accept `random`/`unset` to draw a fresh value on
  each invocation, while preserving all other stored settings. The selected
  value is saved in the emitted self-contained seed, which replays that exact
  render. Width and height are explicit dimensions and are not randomizable.
- Version 3 through 10 seeds remain readable. Migrate their older zoom scale and
  crop keys to normalized zoom and offset keys, rename wave-edge settings, and
  convert legacy cloud/glue scales. Versions through 8 store wave amplitude and
  frequency on older scales, and their `left`/`right` wave-side values should
  migrate to `start`/`end` without changing the rendered side. Version 3 also
  lacks rotation, zoom, offsets, and wave opacity. Version 9 also stores
  `glue_spread` on its prior `0.1`-`0.8` scale; normalize it when decoding.
  Migrate the legacy `edge-to-edge` wave-end value to `full`.
- `eval` reports settings in `EVAL_SETTINGS` order. For entropy-only seeds, use
  the same randomization and `resolve_wave_options` logic as `create`/render.
- Do not add seed-prefix or backward-compatibility layers unless explicitly
  requested; current seeds have no textual prefix.

Add focused tests in `tests/test_seed.py` for payload round trips and malformed
or entropy-only inputs, and CLI tests for evaluation/replay behavior.
