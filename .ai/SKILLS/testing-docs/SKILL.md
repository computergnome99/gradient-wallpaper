---
name: testing-docs
description: Test commands, regression-test patterns, and user documentation expectations.
---

# Testing and documentation

- Run the standard test suite with `python -m unittest discover -s tests`.
- Put renderer and CLI regression tests in `tests/test_render.py`; test seed
  serialization in `tests/test_seed.py`.
- Prefer a few behavioral tests that would fail without the change. For seeded
  behavior, test both repeatability and that meaningful changes in input
  settings affect the result.
- After editing Python files, run the focused tests or the full unittest
  command and check diagnostics where available.
- Update `README.md` for user-visible CLI flags, command behavior, install/run
  instructions, seed semantics, or release assets.
- Keep examples consistent with the actual CLI (`create`, `eval`, and the
  prefixless self-contained seed format). Do not document old formats as
  supported.
