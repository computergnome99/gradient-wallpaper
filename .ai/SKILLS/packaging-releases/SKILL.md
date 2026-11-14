---
name: packaging-releases
description: Local source execution, standalone builds, CI, and platform release artifacts.
---

# Packaging and releases

- `pyproject.toml` defines package metadata, runtime dependencies, the
  `gradient-wallpaper` console script, and optional PyInstaller build
  dependency.
- From the repository root, `python -m gradient_wallpaper` runs directly after
  runtime dependencies are installed.
- `python build.py` creates/reuses `.venv`, installs the project build extra,
  and creates a one-file executable in `dist/`. `run.py` is the PyInstaller
  entry point.
- `build/`, `dist/`, `.venv/`, bytecode, and packaging metadata are ignored by
  Git.
- The test workflow runs the suite on Python 3.10 and 3.12. The release workflow
  tests on Python 3.12, then builds native binaries on GitHub-hosted Windows,
  Linux x86_64/ARM64, and macOS Intel/Apple Silicon runners when a `v*` tag is
  pushed.
- Release assets are unsigned standalone executables. Do not imply that
  binaries are notarized or code-signed.
- Keep release actions on maintained official `actions/*` versions. A release
  job needs `contents: write`; normal test jobs should not request write
  permissions.
