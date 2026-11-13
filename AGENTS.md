# Agent guidance

Before changing the project, read the [skills index](.ai/SKILLS/README.md)
and the skill files relevant to your task.

| Skill                     | Use it for                                                                        | Path                                                                               |
| ------------------------- | --------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| Project overview          | Current architecture, supported behavior, dependencies, and key files.            | [`.ai/SKILLS/project-overview/SKILL.md`](.ai/SKILLS/project-overview/SKILL.md)     |
| Python and CLI            | Python conventions, argument parsing, validation, and command behavior.           | [`.ai/SKILLS/python-cli/SKILL.md`](.ai/SKILLS/python-cli/SKILL.md)                 |
| Rendering                 | Image-generation pipeline, blending, visual effects, and deterministic rendering. | [`.ai/SKILLS/rendering/SKILL.md`](.ai/SKILLS/rendering/SKILL.md)                   |
| Seeds                     | Seed encoding, settings, replay guarantees, and `eval` output.                    | [`.ai/SKILLS/seeds/SKILL.md`](.ai/SKILLS/seeds/SKILL.md)                           |
| Testing and documentation | Regression tests, validation, test commands, and README conventions.              | [`.ai/SKILLS/testing-docs/SKILL.md`](.ai/SKILLS/testing-docs/SKILL.md)             |
| Packaging and releases    | Source execution, executable builds, CI, and platform release assets.             | [`.ai/SKILLS/packaging-releases/SKILL.md`](.ai/SKILLS/packaging-releases/SKILL.md) |

## Common commands

Run these from the repository root. Python 3.10 or later is required.

| Task                                                                | Command                                |
| ------------------------------------------------------------------- | -------------------------------------- |
| Install the project and runtime dependencies for source development | `python -m pip install -e .`           |
| Show CLI help                                                       | `python -m gradient_wallpaper --help`  |
| Run the test suite                                                  | `python -m unittest discover -s tests` |
| Build a standalone executable                                       | `python build.py`                      |

The build command creates or reuses `.venv`, installs the build dependencies,
and writes the executable to `dist/`.

Keep changes focused, preserve deterministic seed behavior, update the README
for user-visible CLI or packaging changes, and run relevant tests before
finishing.
