---
name: seeds
description: Seed payload structure, entropy handling, replay guarantees, and evaluation output.
---

# Seeds and reproducibility

Seed logic is in `gradient_wallpaper/seed.py`; creation and evaluation are
coordinated by `gradient_wallpaper/cli.py`.

- A self-contained seed is unpadded URL-safe Base64 JSON with an internal
  integer `version`, an `entropy` string, and a complete `settings` object.
  There is no textual prefix.
- `SeedSettings` is the authoritative set of persisted rendering fields.
  Update it whenever a new rendering setting is introduced.
- `encode_seed` and `decode_seed` must remain inverses for valid current
  payloads. Validate exact setting keys and value types when decoding.
- A non-self-contained input is treated as entropy text. `create` derives
  omitted visual settings deterministically from it, then prints a
  self-contained seed that can replay the result.
- When a self-contained seed is combined with explicit options, apply those
  options over the stored settings and emit a new self-contained seed.
- `eval` reports settings in `EVAL_SETTINGS` order. For entropy-only seeds, use
  the same randomization and `resolve_wave_options` logic as `create`/render.
- Do not add seed-prefix or backward-compatibility layers unless explicitly
  requested; current seeds have no textual prefix.

Add focused tests in `tests/test_seed.py` for payload round trips and malformed
or entropy-only inputs, and CLI tests for evaluation/replay behavior.
