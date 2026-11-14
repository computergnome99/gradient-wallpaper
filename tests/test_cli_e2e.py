from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image

from gradient_wallpaper.seed import decode_seed


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASE_ARGS = (
    "--width", "48",
    "--height", "32",
    "--colors",
    "#0F1428",
    "#3264AA",
    "#50B4D2",
    "#C84682",
    "#F0BE50",
    "#FAF5E6",
    "--color-order", "input",
    "--wave-amplitude", "0.15",
    "--wave-frequency", "2.2",
    "--wave-edge-strength", "0.75",
    "--wave-opacity", "0.9",
    "--wave-edge", "shadow",
    "--wave-ends", "fade",
    "--wave-orientation", "auto",
    "--wave-side", "auto",
    "--wave-rotation", "0",
    "--zoom", "0",
    "--offset-x", "0",
    "--offset-y", "0",
    "--angle", "20",
    "--dither", "0.2",
    "--cloud-spread", "0.45",
    "--glue-points", "2",
    "--glue-strength", "0.28",
    "--glue-spread", "0.35",
    "--halftone-strength", "0.25",
    "--grain-strength", "0.1",
)

OVERRIDES = (
    ("width", ("--width", "56"), {"width": 56}),
    ("height", ("--height", "40"), {"height": 40}),
    ("format", ("--format", "webp"), {}, "WEBP"),
    (
        "colors",
        ("--colors", "#AABBCC", "#112233"),
        {"colors": ["#AABBCC", "#112233"]},
    ),
    ("color-order", ("--color-order", "hue"), {"color_order": "hue"}),
    ("wave-amplitude", ("--wave-amplitude", "0.32"), {"wave_amplitude": 0.32}),
    ("wave-frequency", ("--wave-frequency", "3.5"), {"wave_frequency": 3.5}),
    (
        "wave-edge-strength",
        ("--wave-edge-strength", "0.4"),
        {"wave_edge_strength": 0.4},
    ),
    ("wave-opacity", ("--wave-opacity", "0.55"), {"wave_opacity": 0.55}),
    ("wave-edge-auto", ("--wave-edge", "auto"), {"wave_edge": "auto"}),
    ("wave-edge-underglow", ("--wave-edge", "underglow"), {"wave_edge": "underglow"}),
    ("wave-edge-aberration", ("--wave-edge", "aberration"), {"wave_edge": "aberration"}),
    (
        "wave-ends-edge-to-edge",
        ("--wave-ends", "edge-to-edge"),
        {"wave_ends": "edge-to-edge"},
    ),
    ("wave-ends-auto", ("--wave-ends", "auto"), {"wave_ends": "auto"}),
    (
        "wave-orientation-horizontal",
        ("--wave-orientation", "horizontal"),
        {"wave_orientation": "horizontal"},
    ),
    (
        "wave-orientation-vertical",
        ("--wave-orientation", "vertical"),
        {"wave_orientation": "vertical"},
    ),
    ("wave-side-left", ("--wave-side", "left"), {"wave_side": "left"}),
    ("wave-side-right", ("--wave-side", "right"), {"wave_side": "right"}),
    ("wave-rotation", ("--wave-rotation", "-8"), {"wave_rotation": -8}),
    ("zoom", ("--zoom", "0.6"), {"zoom": 0.6}),
    ("offset-x", ("--offset-x", "0.5"), {"offset_x": 0.5}),
    ("offset-y", ("--offset-y", "-0.5"), {"offset_y": -0.5}),
    ("angle", ("--angle", "100"), {"angle": 100}),
    ("dither", ("--dither", "0.8"), {"dither": 0.8}),
    ("cloud-spread", ("--cloud-spread", "0.85"), {"cloud_spread": 0.85}),
    ("glue-points", ("--glue-points", "4"), {"glue_points": 4}),
    ("glue-strength", ("--glue-strength", "0.8"), {"glue_strength": 0.8}),
    ("glue-spread", ("--glue-spread", "0.7"), {"glue_spread": 0.7}),
    (
        "halftone-strength",
        ("--halftone-strength", "0.8"),
        {"halftone_strength": 0.8},
    ),
    ("grain-strength", ("--grain-strength", "0.75"), {"grain_strength": 0.75}),
)


def _run_cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "gradient_wallpaper", *arguments],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=90,
    )


class CliEndToEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_directory = tempfile.TemporaryDirectory()
        cls.output_dir = Path(cls.temp_directory.name)
        cls.base_output = cls.output_dir / "base.png"
        result = _run_cli(
            "create",
            *BASE_ARGS,
            "--seed", "cli-e2e-fixed",
            "--output", str(cls.base_output),
        )
        if result.returncode:
            raise RuntimeError(
                f"base CLI invocation failed:\n{result.stdout}\n{result.stderr}"
            )
        cls.base_seed = result.stdout.split("seed: ", 1)[1].strip()
        decoded = decode_seed(cls.base_seed)
        if decoded is None:
            raise RuntimeError("CLI did not return a self-contained seed")
        _, cls.base_settings = decoded

    @classmethod
    def tearDownClass(cls):
        cls.temp_directory.cleanup()

    def test_flag_overrides_run_as_independent_cli_processes(self):
        def run_override(case):
            name, options, expected, *expected_format = case
            output_path = self.output_dir / f"{name}.png"
            result = _run_cli(
                *options,
                "--seed", self.base_seed,
                "--output", str(output_path),
            )
            if result.returncode:
                raise AssertionError(
                    f"{name} CLI invocation failed:\n"
                    f"{result.stdout}\n{result.stderr}"
                )
            seed = result.stdout.split("seed: ", 1)[1].strip()
            decoded = decode_seed(seed)
            if decoded is None:
                raise AssertionError(f"{name} did not return a self-contained seed")
            _, settings = decoded
            for key, value in expected.items():
                if settings[key] != value:
                    raise AssertionError(
                        f"{name}: expected {key}={value!r}, got {settings[key]!r}"
                    )
            changed_keys = set(expected)
            for key, value in self.base_settings.items():
                if key not in changed_keys and settings[key] != value:
                    raise AssertionError(
                        f"{name}: unrelated setting {key} changed"
                    )
            with Image.open(output_path) as image:
                expected_size = (
                    expected.get("width", self.base_settings["width"]),
                    expected.get("height", self.base_settings["height"]),
                )
                if image.size != expected_size:
                    raise AssertionError(
                        f"{name}: expected image size {expected_size}, got {image.size}"
                    )
                image_format = expected_format[0] if expected_format else "PNG"
                if image.format != image_format:
                    raise AssertionError(
                        f"{name}: expected {image_format}, got {image.format}"
                    )
            return name

        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = [executor.submit(run_override, case) for case in OVERRIDES]
            completed = [future.result() for future in futures]
        self.assertEqual(set(completed), {case[0] for case in OVERRIDES})

    def test_self_contained_seed_replays_through_cli(self):
        replay_output = self.output_dir / "replay.png"
        result = _run_cli(
            "--seed", self.base_seed,
            "--output", str(replay_output),
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        with Image.open(self.base_output) as base, Image.open(replay_output) as replay:
            np.testing.assert_array_equal(np.asarray(base), np.asarray(replay))

    def test_numeric_random_sentinel_rerolls_only_selected_setting(self):
        output_path = self.output_dir / "random-amplitude.png"
        result = _run_cli(
            "--wave-amplitude", "random",
            "--seed", self.base_seed,
            "--output", str(output_path),
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        seed = result.stdout.split("seed: ", 1)[1].strip()
        decoded = decode_seed(seed)
        self.assertIsNotNone(decoded)
        _, settings = decoded
        self.assertGreaterEqual(settings["wave_amplitude"], 0.06)
        self.assertLessEqual(settings["wave_amplitude"], 0.18)
        self.assertNotEqual(
            settings["wave_amplitude"], self.base_settings["wave_amplitude"]
        )
        for key, value in self.base_settings.items():
            if key != "wave_amplitude":
                self.assertEqual(settings[key], value, f"unexpected change to {key}")

        replay_path = self.output_dir / "random-amplitude-replay.png"
        replay = _run_cli("--seed", seed, "--output", str(replay_path))
        self.assertEqual(replay.returncode, 0, msg=replay.stderr)
        with Image.open(output_path) as rerolled, Image.open(replay_path) as replayed:
            np.testing.assert_array_equal(np.asarray(rerolled), np.asarray(replayed))

    def test_multiple_numeric_random_sentinels_resample_on_each_run(self):
        arguments = (
            "--wave-amplitude", "random",
            "--wave-frequency", "random",
            "--angle", "unset",
            "--glue-points", "random",
            "--seed", self.base_seed,
        )
        results = []
        decoded_settings = []
        for index in range(2):
            output_path = self.output_dir / f"reroll-{index}.png"
            result = _run_cli(*arguments, "--output", str(output_path))
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            results.append(result.stdout.split("seed: ", 1)[1].strip())
            decoded = decode_seed(results[-1])
            self.assertIsNotNone(decoded)
            _, settings = decoded
            decoded_settings.append(settings)
            self.assertGreaterEqual(settings["wave_amplitude"], 0.06)
            self.assertLessEqual(settings["wave_amplitude"], 0.18)
            self.assertGreaterEqual(settings["wave_frequency"], 1.5)
            self.assertLessEqual(settings["wave_frequency"], 4)
            self.assertGreaterEqual(settings["angle"], -360)
            self.assertLessEqual(settings["angle"], 360)
            self.assertIn(settings["glue_points"], (2, 3))
            for key, value in self.base_settings.items():
                if key not in {
                    "wave_amplitude",
                    "wave_frequency",
                    "angle",
                    "glue_points",
                }:
                    self.assertEqual(settings[key], value, f"unexpected change to {key}")

        self.assertNotEqual(results[0], results[1])
        self.assertNotEqual(
            decoded_settings[0]["wave_amplitude"],
            decoded_settings[1]["wave_amplitude"],
        )
        self.assertNotEqual(
            decoded_settings[0]["wave_frequency"],
            decoded_settings[1]["wave_frequency"],
        )

    def test_eval_subcommand_reports_cli_seed_settings(self):
        result = _run_cli("eval", "--seed", self.base_seed)
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("Wave edge strength", result.stdout)
        self.assertIn("Wave edge", result.stdout)
        self.assertIn("Cloud spread", result.stdout)
        self.assertIn("Glue strength", result.stdout)


if __name__ == "__main__":
    unittest.main()
