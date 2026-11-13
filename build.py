from __future__ import annotations

import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_DIR = ROOT / ".venv"


def main() -> None:
    if not ENV_DIR.exists():
        venv.EnvBuilder(with_pip=True).create(ENV_DIR)

    python = (
        ENV_DIR / "Scripts" / "python.exe"
        if sys.platform == "win32"
        else ENV_DIR / "bin" / "python"
    )
    subprocess.run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "-e",
            ".[build]",
        ],
        cwd=ROOT,
        check=True,
    )
    (ROOT / "build" / "pyinstaller").mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            str(python),
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--onefile",
            "--name",
            "gradient-wallpaper",
            "--distpath",
            str(ROOT / "dist"),
            "--workpath",
            str(ROOT / "build" / "pyinstaller"),
            "--specpath",
            str(ROOT / "build" / "pyinstaller"),
            str(ROOT / "run.py"),
        ],
        cwd=ROOT,
        check=True,
    )
    executable = (
        ROOT / "dist" / "gradient-wallpaper.exe"
        if sys.platform == "win32"
        else ROOT / "dist" / "gradient-wallpaper"
    )
    print(f"\nBuilt executable: {executable}")


if __name__ == "__main__":
    main()
