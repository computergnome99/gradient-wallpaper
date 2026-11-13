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
        self.assertEqual(payload["version"], 3)

    def test_plain_text_seed_is_entropy_not_a_self_contained_seed(self):
        self.assertIsNone(decode_seed("catppuccin"))


if __name__ == "__main__":
    unittest.main()
