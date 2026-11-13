---
name: python-cli
description: Python coding style, argument parsing, validation, and command behavior.
---

# Python and CLI conventions

- Target Python 3.10+. Use type annotations for public and nontrivial helper
  functions; follow existing naming (`snake_case`, private helpers prefixed
  with `_`).
- Keep argument parsing and user-facing errors in `gradient_wallpaper/cli.py`.
  Use `argparse` types/choices and `parser.error` for invalid command-line
  values rather than silent fallbacks.
- Keep CLI option names kebab-case and internal settings snake_case.
- The parser defaults to `create`; preserve both implicit and explicit
  `create` forms. `eval` takes a seed and prints a fixed-order settings table.
- When adding a setting, update `DEFAULT_SETTINGS`, omitted-setting
  randomization, CLI options and validation, the renderer call, `SeedSettings`,
  `EVAL_SETTINGS`, and README/help as applicable.
- Omitted values without a self-contained seed are generated deterministically
  from the seed entropy. Keep that behavior reproducible.
- Reuse existing color parsing, color ordering, bounded numeric validators,
  and seed-resolution helpers instead of duplicating them.
- Do not add a dependency for functionality available in the standard library,
  NumPy, or Pillow without a clear need.
