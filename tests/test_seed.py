import base64
import json
import unittest

from gradient_wallpaper.cli import DEFAULT_SETTINGS
from gradient_wallpaper.seed import decode_seed, encode_seed


class SeedTests(unittest.TestCase):
    def test_seed_round_trips_without_a_prefix(self):
        settings = dict(DEFAULT_SETTINGS)
        settings["glue_points"] = 3
        settings["glue_colors"] = 1
        settings["glue_strength"] = 0.12
        settings["glue_spread"] = 0.4

        token = encode_seed("entropy", settings)

        self.assertFalse(token.startswith("gw"))
        self.assertEqual(decode_seed(token), ("entropy", settings))
        padding = "=" * (-len(token) % 4)
        payload = json.loads(base64.urlsafe_b64decode(token + padding))
        self.assertEqual(payload["version"], 6)

    def test_version_three_seeds_get_neutral_crop_settings(self):
        settings = dict(DEFAULT_SETTINGS)
        settings["width"] = 2560
        for key in (
            "wave_rotation",
            "zoom",
            "offset_x",
            "offset_y",
            "wave_opacity",
        ):
            settings.pop(key)
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

    def test_version_four_and_five_seeds_migrate_zoom_and_offsets(self):
        for version in (4, 5):
            with self.subTest(version=version):
                settings = dict(DEFAULT_SETTINGS)
                settings.update(
                    wave_rotation=8.0,
                    zoom=1.25,
                    wave_opacity=0.4,
                    offset_x=-0.5,
                    offset_y=0.25,
                )
                settings["crop_x"] = settings.pop("offset_x")
                settings["crop_y"] = settings.pop("offset_y")
                if version == 4:
                    settings.pop("wave_opacity")
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
                self.assertEqual(
                    upgraded_settings["wave_opacity"],
                    1.0 if version == 4 else 0.4,
                )

    def test_plain_text_seed_is_entropy_not_a_self_contained_seed(self):
        self.assertIsNone(decode_seed("catppuccin"))


if __name__ == "__main__":
    unittest.main()
