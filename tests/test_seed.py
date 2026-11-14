import base64
import json
import unittest

from gradient_wallpaper.cli import DEFAULT_SETTINGS
from gradient_wallpaper.seed import decode_seed, encode_seed


def _settings_for_version(version):
    settings = dict(DEFAULT_SETTINGS)
    settings["wave_depth"] = settings.pop("wave_edge_strength")
    if version <= 6:
        settings["wave_mode"] = settings.pop("wave_edge")
        settings["glue_colors"] = 2
        settings["cloud_spread"] = 0.18
        settings["glue_strength"] = 0.07
    if version <= 5:
        settings["zoom"] = 1.25
        settings["crop_x"] = settings.pop("offset_x")
        settings["crop_y"] = settings.pop("offset_y")
    if version == 3:
        for key in ("wave_rotation", "zoom", "crop_x", "crop_y", "wave_opacity"):
            settings.pop(key)
    elif version == 4:
        settings.pop("wave_opacity")
    return settings


class SeedTests(unittest.TestCase):
    def test_seed_round_trips_without_a_prefix(self):
        settings = dict(DEFAULT_SETTINGS)
        settings["glue_points"] = 3
        settings["glue_strength"] = 0.48
        settings["glue_spread"] = 0.4

        token = encode_seed("entropy", settings)

        self.assertFalse(token.startswith("gw"))
        self.assertEqual(decode_seed(token), ("entropy", settings))
        padding = "=" * (-len(token) % 4)
        payload = json.loads(base64.urlsafe_b64decode(token + padding))
        self.assertEqual(payload["version"], 8)

    def test_version_three_seeds_get_neutral_crop_settings(self):
        settings = _settings_for_version(3)
        settings["width"] = 2560
        payload = {
            "version": 3,
            "entropy": "old-entropy",
            "settings": settings,
        }
        data = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")
        token = base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")

        decoded = decode_seed(token)

        self.assertIsNotNone(decoded)
        entropy, upgraded_settings = decoded
        self.assertEqual(entropy, "old-entropy")
        self.assertEqual(upgraded_settings["width"], 2560)
        self.assertEqual(upgraded_settings["wave_rotation"], 0.0)
        self.assertEqual(upgraded_settings["zoom"], 0.0)
        self.assertEqual(upgraded_settings["offset_x"], 0.0)
        self.assertEqual(upgraded_settings["offset_y"], 0.0)
        self.assertEqual(upgraded_settings["wave_opacity"], 1.0)
        self.assertEqual(upgraded_settings["wave_edge"], "auto")
        self.assertNotIn("glue_colors", upgraded_settings)
        self.assertAlmostEqual(upgraded_settings["cloud_spread"], 0.15 / 0.47)
        self.assertAlmostEqual(upgraded_settings["glue_strength"], 0.28)

    def test_version_four_and_five_seeds_migrate_zoom_and_offsets(self):
        for version in (4, 5):
            with self.subTest(version=version):
                settings = _settings_for_version(version)
                settings.update(
                    wave_rotation=8.0,
                    crop_x=-0.5,
                    crop_y=0.25,
                    wave_mode="chromatic-aberration",
                )
                if version == 5:
                    settings["wave_opacity"] = 0.4
                payload = {
                    "version": version,
                    "entropy": "old-entropy",
                    "settings": settings,
                }
                data = json.dumps(
                    payload,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=True,
                ).encode("utf-8")
                token = base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")

                decoded = decode_seed(token)

                self.assertIsNotNone(decoded)
                entropy, upgraded_settings = decoded
                self.assertEqual(entropy, "old-entropy")
                self.assertEqual(upgraded_settings["wave_rotation"], 8.0)
                self.assertEqual(upgraded_settings["zoom"], 0.25)
                self.assertEqual(upgraded_settings["offset_x"], -0.5)
                self.assertEqual(upgraded_settings["offset_y"], 0.25)
                self.assertEqual(upgraded_settings["wave_edge"], "aberration")
                self.assertNotIn("glue_colors", upgraded_settings)
                self.assertAlmostEqual(
                    upgraded_settings["cloud_spread"], 0.15 / 0.47
                )
                self.assertAlmostEqual(upgraded_settings["glue_strength"], 0.28)
                self.assertEqual(
                    upgraded_settings["wave_opacity"],
                    1.0 if version == 4 else 0.4,
                )

    def test_version_six_seeds_migrate_edge_names_and_normalized_scales(self):
        settings = _settings_for_version(6)
        settings.update(
            wave_mode="chromatic-aberration",
            cloud_spread=0.18,
            glue_strength=0.07,
            offset_x=-0.5,
            offset_y=0.25,
        )
        payload = {
            "version": 6,
            "entropy": "old-entropy",
            "settings": settings,
        }
        data = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")
        token = base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")

        decoded = decode_seed(token)

        self.assertIsNotNone(decoded)
        _, upgraded_settings = decoded
        self.assertEqual(upgraded_settings["wave_edge"], "aberration")
        self.assertAlmostEqual(upgraded_settings["cloud_spread"], 0.15 / 0.47)
        self.assertAlmostEqual(upgraded_settings["glue_strength"], 0.28)
        self.assertEqual(upgraded_settings["offset_x"], -0.5)
        self.assertEqual(upgraded_settings["offset_y"], 0.25)
        self.assertNotIn("glue_colors", upgraded_settings)

    def test_version_seven_seed_migrates_wave_edge_strength_name(self):
        settings = _settings_for_version(7)
        settings["wave_depth"] = 0.4
        payload = {
            "version": 7,
            "entropy": "old-entropy",
            "settings": settings,
        }
        data = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")
        token = base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")

        decoded = decode_seed(token)

        self.assertIsNotNone(decoded)
        _, upgraded_settings = decoded
        self.assertEqual(upgraded_settings["wave_edge_strength"], 0.4)
        self.assertEqual(upgraded_settings["cloud_spread"], DEFAULT_SETTINGS["cloud_spread"])
        self.assertEqual(upgraded_settings["glue_strength"], DEFAULT_SETTINGS["glue_strength"])
        self.assertNotIn("wave_depth", upgraded_settings)

    def test_plain_text_seed_is_entropy_not_a_self_contained_seed(self):
        self.assertIsNone(decode_seed("catppuccin"))


if __name__ == "__main__":
    unittest.main()
