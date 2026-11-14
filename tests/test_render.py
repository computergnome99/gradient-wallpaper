import colorsys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from gradient_wallpaper.render import (
    _apply_wave_highlight,
    _apply_wave_shadow,
    _apply_wave_underglow,
    _apply_aberration,
    _apply_glue_layer,
    _apply_halftone_dither,
    _apply_film_grain,
    _create_wave_layers,
    _create_wave_underglow_mask,
    _classify_palette,
    _create_aberration_colors,
    _darkest_palette_color,
    _create_point_cloud,
    _screen_blend,
    order_colors,
    parse_color,
    render,
)


class RenderTests(unittest.TestCase):
    def test_create_help_groups_settings_by_purpose(self):
        from gradient_wallpaper.cli import build_create_parser

        help_text = build_create_parser().format_help()

        for heading in (
            "Output image:",
            "Palette and seed:",
            "Wave:",
            "Framing:",
            "Gradient and blending:",
            "Post-effects:",
        ):
            self.assertIn(heading, help_text)
        self.assertIn("--offset-x", help_text)
        self.assertIn("--offset-y", help_text)
        self.assertIn("--wave-edge", help_text)
        self.assertIn("percentage progress bar on stderr", help_text)
        self.assertIn("rerolls are fresh each invocation", help_text)
        self.assertIn("aberration", help_text)
        self.assertNotIn("--wave-mode", help_text)
        self.assertNotIn("--wave-depth", help_text)
        self.assertNotIn("--glue-colors", help_text)
        self.assertNotIn("--crop-x", help_text)
        self.assertNotIn("--crop-y", help_text)

    def test_random_settings_avoid_flat_waves_and_tiny_cloud_points(self):
        from gradient_wallpaper.cli import (
            _default_settings,
            _randomize_missing_settings,
            build_create_parser,
        )

        args = build_create_parser().parse_args([])
        amplitudes = []
        frequencies = []
        cloud_spreads = []
        opacities = []
        for index in range(64):
            settings = _default_settings()
            _randomize_missing_settings(settings, f"wave-{index}", args)
            amplitudes.append(settings["wave_amplitude"])
            frequencies.append(settings["wave_frequency"])
            cloud_spreads.append(settings["cloud_spread"])
            opacities.append(settings["wave_opacity"])

        self.assertGreater(float(np.mean(amplitudes)), 0.10)
        self.assertLess(float(np.mean(amplitudes)), 0.14)
        self.assertGreater(float(np.mean(frequencies)), 2.5)
        self.assertLess(float(np.mean(frequencies)), 3.2)
        self.assertGreaterEqual(min(amplitudes), 0.06)
        self.assertLessEqual(max(amplitudes), 0.18)
        self.assertGreaterEqual(min(frequencies), 1.5)
        self.assertLessEqual(max(frequencies), 4.0)
        self.assertGreaterEqual(min(cloud_spreads), (0.12 - 0.03) / 0.47)
        self.assertGreater(float(np.mean(cloud_spreads)), 0.6)
        self.assertLessEqual(max(cloud_spreads), 1)
        self.assertGreaterEqual(min(opacities), 0.92)
        self.assertGreater(float(np.mean(opacities)), 0.98)
        self.assertLessEqual(max(opacities), 1.0)

    def test_parse_color_accepts_short_and_long_hex(self):
        self.assertEqual(parse_color("#abc"), (170, 187, 204))
        self.assertEqual(parse_color("123456"), (18, 52, 86))

    def test_hue_order_uses_shortest_arc_across_hue_wrap(self):
        red = (255, 0, 0)
        orange = (255, 128, 0)
        blue = (0, 0, 255)
        self.assertEqual(order_colors([red, orange, blue], "hue"), [blue, red, orange])

    def test_same_seed_reproduces_identical_pixels(self):
        options = dict(
            width=64,
            height=36,
            colors=[(10, 20, 30), (100, 110, 120), (220, 180, 90)],
            seed="stable",
        )
        first = np.asarray(render(**options))
        second = np.asarray(render(**options))
        np.testing.assert_array_equal(first, second)

    def test_progress_callback_reports_monotonic_render_stages(self):
        events = []
        image = render(
            32,
            20,
            [(10, 20, 30), (100, 110, 120), (220, 180, 90)],
            "progress",
            progress_callback=lambda percent, phase: events.append(
                (percent, phase)
            ),
        )

        self.assertEqual(image.size, (32, 20))
        percentages = [percent for percent, _ in events]
        self.assertEqual(percentages[0], 0)
        self.assertEqual(percentages[-1], 98)
        self.assertEqual(percentages, sorted(percentages))
        phases = {phase for _, phase in events}
        self.assertIn("Background gradient", phases)
        self.assertIn("Wave gradient", phases)
        self.assertIn("Post-processing", phases)

    def test_terminal_progress_display_shows_percent_only_for_tty(self):
        from io import StringIO
        from unittest.mock import patch

        from gradient_wallpaper.cli import _ProgressDisplay

        output = StringIO()
        with patch("sys.stderr") as stderr:
            stderr.isatty.return_value = True
            stderr.write.side_effect = output.write
            stderr.flush.side_effect = output.flush
            with _ProgressDisplay() as progress:
                progress.update(25, "Rendering")
                progress.update(80, "Saving")
        self.assertIn("25%", output.getvalue())
        self.assertIn("80%", output.getvalue())
        self.assertIn("100%", output.getvalue())
        rendered_lines = [
            line.rstrip("\n") for line in output.getvalue().split("\r")[1:]
        ]
        self.assertEqual(
            len(rendered_lines[-1]),
            max(len(line) for line in rendered_lines[:-1]),
        )

        output = StringIO()
        with patch("sys.stderr") as stderr:
            stderr.isatty.return_value = False
            stderr.write.side_effect = output.write
            with _ProgressDisplay() as progress:
                progress.update(25, "Rendering")
        self.assertEqual(output.getvalue(), "")

    def test_normalized_cloud_spread_maps_to_supported_internal_range(self):
        from unittest.mock import patch

        options = dict(
            width=16,
            height=8,
            colors=[(20, 40, 80), (120, 160, 200), (240, 180, 90)],
            seed="cloud-spread-scale",
            wave_edge="shadow",
            glue_points=0,
            glue_strength=0,
            dither=0,
        )
        for scale, expected_spread in ((0, 0.03), (1, 0.5)):
            with self.subTest(scale=scale), patch(
                "gradient_wallpaper.render._create_point_cloud",
                wraps=_create_point_cloud,
            ) as point_cloud:
                render(**options, cloud_spread=scale)
                self.assertEqual(point_cloud.call_count, 2)
                for call in point_cloud.call_args_list:
                    self.assertAlmostEqual(call.args[4], expected_spread)

    def test_wave_rotation_tilts_horizontal_and_vertical_masks(self):
        for orientation in ("horizontal", "vertical"):
            with self.subTest(orientation=orientation):
                options = dict(
                    width=100,
                    height=100,
                    wave_amplitude=0,
                    wave_frequency=0,
                    orientation=orientation,
                    wave_ends="edge-to-edge",
                )
                unrotated, _, _ = _create_wave_layers(
                    **options, rng=np.random.default_rng(42)
                )
                rotated, highlight, _ = _create_wave_layers(
                    **options,
                    rng=np.random.default_rng(42),
                    wave_rotation=15,
                )
                np.testing.assert_array_equal(
                    rotated,
                    _create_wave_layers(
                        **options,
                        rng=np.random.default_rng(42),
                        wave_rotation=15,
                    )[0],
                )
                self.assertFalse(np.array_equal(unrotated, rotated))

                if orientation == "horizontal":
                    left_edge = int(np.argmax(rotated[:, 20] > 0.5))
                    right_edge = int(np.argmax(rotated[:, 80] > 0.5))
                    left_highlight = int(np.argmax(highlight[:, 20]))
                    right_highlight = int(np.argmax(highlight[:, 80]))
                else:
                    left_edge = int(np.argmax(rotated[20] > 0.5))
                    right_edge = int(np.argmax(rotated[80] > 0.5))
                    left_highlight = int(np.argmax(highlight[20]))
                    right_highlight = int(np.argmax(highlight[80]))
                self.assertGreater(right_edge, left_edge)
                self.assertLessEqual(abs(left_highlight - left_edge), 4)
                self.assertLessEqual(abs(right_highlight - right_edge), 4)

    def test_zoom_overscans_and_crops_without_changing_output_size(self):
        options = dict(
            width=40,
            height=24,
            colors=[(20, 40, 80), (180, 90, 120), (240, 200, 80)],
            seed="zoom-crop",
        )
        base = np.asarray(render(**options))
        no_zoom = np.asarray(
            render(**options, zoom=0, offset_x=-1, offset_y=1)
        )
        np.testing.assert_array_equal(base, no_zoom)

        zoomed = render(**options, zoom=0.25, offset_x=0.8, offset_y=-0.6)
        repeat = render(**options, zoom=0.25, offset_x=0.8, offset_y=-0.6)
        self.assertEqual(zoomed.size, (40, 24))
        np.testing.assert_array_equal(np.asarray(zoomed), np.asarray(repeat))
        self.assertFalse(np.array_equal(base, np.asarray(zoomed)))

        full_zoom = render(**options, zoom=1, offset_x=-1, offset_y=1)
        self.assertEqual(full_zoom.size, (40, 24))
        self.assertFalse(np.array_equal(base, np.asarray(full_zoom)))

    def test_wave_opacity_zero_disables_wave_effects(self):
        options = dict(
            width=48,
            height=28,
            colors=[
                (15, 20, 40),
                (50, 100, 170),
                (80, 180, 210),
                (200, 70, 130),
                (240, 190, 80),
                (250, 245, 230),
            ],
            seed="wave-opacity",
        )
        disabled_images = []
        for mode in ("shadow", "underglow", "aberration"):
            with self.subTest(mode=mode):
                disabled = np.asarray(
                    render(**options, wave_edge=mode, wave_opacity=0)
                )
                disabled_images.append(disabled)
                zero_depth = np.asarray(
                    render(
                        **options,
                        wave_edge=mode,
                        wave_opacity=0,
                        wave_edge_strength=0,
                    )
                )
                full = np.asarray(
                    render(**options, wave_edge=mode, wave_opacity=1)
                )
                np.testing.assert_array_equal(disabled, zero_depth)
                self.assertFalse(np.array_equal(disabled, full))
        for disabled in disabled_images[1:]:
            np.testing.assert_array_equal(disabled_images[0], disabled)

    def test_wave_edges_can_be_forced_and_repeat_with_the_same_seed(self):
        from unittest.mock import patch

        colors = [
            (15, 20, 40),
            (50, 100, 170),
            (80, 180, 210),
            (200, 70, 130),
            (240, 190, 80),
            (250, 245, 230),
        ]
        with (
            patch(
                "gradient_wallpaper.render._apply_wave_shadow",
                wraps=_apply_wave_shadow,
            ) as shadow,
            patch(
                "gradient_wallpaper.render._apply_wave_underglow",
                wraps=_apply_wave_underglow,
            ) as underglow,
            patch(
                "gradient_wallpaper.render._apply_wave_highlight",
                wraps=_apply_wave_highlight,
            ) as highlight,
            patch(
                "gradient_wallpaper.render._apply_aberration",
                wraps=_apply_aberration,
            ) as aberration,
        ):
            for mode in ("shadow", "underglow", "aberration"):
                options = dict(
                    width=32,
                    height=24,
                    colors=colors,
                    seed="forced-mode",
                    wave_edge=mode,
                    dither=0,
                )
                first = np.asarray(render(**options))
                repeat = np.asarray(render(**options))
                np.testing.assert_array_equal(first, repeat)

            self.assertEqual(shadow.call_count, 2)
            self.assertEqual(underglow.call_count, 2)
            self.assertEqual(aberration.call_count, 2)
            self.assertEqual(highlight.call_count, 4)
            self.assertEqual(
                [
                    call.kwargs.get("intensity", 1.0)
                    for call in highlight.call_args_list
                ],
                [1.0, 1.0, 1.0, 1.0],
            )

    def test_aberration_works_with_single_color_palette(self):
        image = render(
            16,
            8,
            [(80, 140, 200)],
            "single-color-aberration",
            wave_edge="aberration",
        )
        self.assertEqual(image.size, (16, 8))

    def test_one_color_stop_renders_a_tonal_gradient(self):
        image = np.asarray(render(32, 16, [(100, 140, 180)], "one"))
        self.assertEqual(image.shape, (16, 32, 3))
        self.assertGreater(int(image.max()), int(image.min()))

    def test_wave_mask_is_lower_half_and_fades_at_both_ends(self):
        mask, highlight, shadow = _create_wave_layers(
            200, 100, np.random.default_rng(42), 0.22, 1
        )
        self.assertEqual(float(mask[:, 0].max()), 0)
        self.assertEqual(float(mask[:, -1].max()), 0)
        self.assertLess(float(mask[5, 100]), 0.05)
        self.assertGreater(float(mask[95, 100]), 0.8)
        self.assertGreater(float(mask[50, 20:-20].std()), 0.05)
        transition = np.count_nonzero((mask[:, 100] > 0.05) & (mask[:, 100] < 0.95))
        self.assertLess(transition, 10)
        edge = int(np.argmax(np.gradient(mask[:, 100])))
        self.assertLess(int(np.argmax(highlight[:, 100])), edge)
        self.assertGreater(float(shadow[mask < 0.2].max()), 0.05)
        self.assertLess(
            float(shadow[mask > 0.8].max()),
            float(shadow[mask < 0.2].max()),
        )

    def test_wave_can_reach_edges_or_run_vertically(self):
        edge_mask, _, _ = _create_wave_layers(
            120,
            80,
            np.random.default_rng(42),
            0.22,
            1,
            wave_ends="edge-to-edge",
        )
        self.assertGreater(float(edge_mask[:, 0].max()), 0.9)
        self.assertGreater(float(edge_mask[:, -1].max()), 0.9)

        vertical_mask, _, _ = _create_wave_layers(
            120,
            80,
            np.random.default_rng(42),
            0.22,
            1,
            orientation="vertical",
            wave_ends="edge-to-edge",
        )
        self.assertEqual(vertical_mask.shape, (80, 120))
        self.assertGreater(float(vertical_mask[0, :].max()), 0.9)
        self.assertGreater(float(vertical_mask[-1, :].max()), 0.9)
        self.assertGreater(float(vertical_mask[40, 20:-20].std()), 0.05)

    def test_underglow_spreads_into_background_and_follows_end_fade(self):
        horizontal_mask = np.zeros((80, 100), dtype=np.float32)
        horizontal_mask[40:] = 1
        horizontal_glow = _create_wave_underglow_mask(
            horizontal_mask, "horizontal"
        )
        self.assertGreater(float(horizontal_glow[39, 50]), 0.9)
        self.assertGreater(
            np.count_nonzero(horizontal_glow[:40, 50] > 0.05), 5
        )
        self.assertFalse(np.any(horizontal_glow[40:]))

        fade = np.linspace(0, 1, horizontal_mask.shape[1], dtype=np.float32)
        faded_mask = horizontal_mask * fade[None, :]
        faded_glow = _create_wave_underglow_mask(faded_mask, "horizontal")
        self.assertLess(float(faded_glow[:, 0].max()), float(faded_glow[:, 50].max()))

        vertical_mask = horizontal_mask.T
        vertical_glow = _create_wave_underglow_mask(vertical_mask, "vertical")
        self.assertGreater(float(vertical_glow[50, 39]), 0.9)
        self.assertFalse(np.any(vertical_glow[:, 40:]))

    def test_underglow_preserves_wave_gradient_palette(self):
        from unittest.mock import patch

        options = dict(
            width=64,
            height=40,
            colors=[
                (15, 20, 40),
                (50, 100, 170),
                (80, 180, 210),
                (200, 70, 130),
                (240, 190, 80),
                (250, 245, 230),
            ],
            seed="same-wave-under-edge-treatments",
            wave_ends="edge-to-edge",
            wave_orientation="horizontal",
            dither=0,
            halftone_strength=0,
            grain_strength=0,
        )
        point_clouds = {}
        for edge in ("shadow", "underglow"):
            outputs = []

            def record_point_cloud(*args, **kwargs):
                result = _create_point_cloud(*args, **kwargs)
                outputs.append(result.copy())
                return result

            with patch(
                "gradient_wallpaper.render._create_point_cloud",
                side_effect=record_point_cloud,
            ):
                render(**options, wave_edge=edge)
            point_clouds[edge] = outputs

        self.assertEqual(len(point_clouds["shadow"]), 2)
        self.assertEqual(len(point_clouds["underglow"]), 2)
        for shadow_cloud, glow_cloud in zip(
            point_clouds["shadow"], point_clouds["underglow"]
        ):
            np.testing.assert_array_equal(shadow_cloud, glow_cloud)

    def test_vertical_wave_foreground_side_controls_highlight_side(self):
        left_mask, left_highlight, _ = _create_wave_layers(
            120,
            80,
            np.random.default_rng(42),
            0.22,
            1,
            orientation="vertical",
            wave_ends="edge-to-edge",
            foreground_side="top",
        )
        right_mask, right_highlight, _ = _create_wave_layers(
            120,
            80,
            np.random.default_rng(42),
            0.22,
            1,
            orientation="vertical",
            wave_ends="edge-to-edge",
            foreground_side="bottom",
        )
        row = 40
        left_edge = int(np.argmax(np.abs(np.gradient(left_mask[row]))))
        right_edge = int(np.argmax(np.abs(np.gradient(right_mask[row]))))
        self.assertLess(int(np.argmax(left_mask[row])), left_edge)
        self.assertGreater(int(np.argmax(right_mask[row])), right_edge)
        self.assertGreater(int(np.argmax(left_highlight[row])), left_edge)
        self.assertLess(int(np.argmax(right_highlight[row])), right_edge)

    def test_wave_edge_strength_controls_raised_lighting(self):
        image = np.full((8, 8, 3), 0.4, dtype=np.float32)
        highlight = np.zeros((8, 8), dtype=np.float32)
        shadow = np.zeros((8, 8), dtype=np.float32)
        highlight[3, 3] = 1
        shadow[4, 4] = 1
        shadow_color = np.array([0.1, 0.2, 0.3], dtype=np.float32)
        accent_color = np.array([0.2, 0.7, 0.1], dtype=np.float32)
        unchanged = _apply_wave_highlight(
            _apply_wave_shadow(image.copy(), shadow, 0, shadow_color), highlight, 0
        )
        unchanged = _apply_wave_underglow(unchanged, shadow, 0, accent_color)
        np.testing.assert_allclose(unchanged, image)
        raised = _apply_wave_highlight(image.copy(), highlight, 1)
        softened = _apply_wave_highlight(image.copy(), highlight, 1, 0.5)
        shadowed = _apply_wave_shadow(image.copy(), shadow, 1, shadow_color)
        glowing = _apply_wave_underglow(image.copy(), shadow, 1, accent_color)
        self.assertGreater(float(raised[3, 3, 0]), float(image[3, 3, 0]))
        self.assertGreater(float(softened[3, 3, 0]), float(image[3, 3, 0]))
        self.assertLess(float(softened[3, 3, 0]), float(raised[3, 3, 0]))
        self.assertTrue(np.all(shadowed[4, 4] < image[4, 4]))
        self.assertTrue(np.all(glowing[4, 4] > image[4, 4]))
        self.assertTrue(np.all(shadowed <= image))

    def test_wave_shadow_strength_softens_at_medium_and_high_values(self):
        image = np.full((1, 1, 3), 0.5, dtype=np.float32)
        shadow = np.ones((1, 1), dtype=np.float32)
        shadow_color = np.zeros(3, dtype=np.float32)

        medium = _apply_wave_shadow(image, shadow, 0.5, shadow_color)
        high = _apply_wave_shadow(image, shadow, 1, shadow_color)

        np.testing.assert_allclose(medium[0, 0], 0.43625)
        np.testing.assert_allclose(high[0, 0], 0.395)
        self.assertTrue(np.all(high[0, 0] > 0.35))

    def test_wave_shadow_uses_darkest_palette_color(self):
        palette = np.asarray([(255, 0, 0), (0, 0, 80), (255, 255, 255)])
        expected = np.asarray(
            [0, 0, ((80 / 255 + 0.055) / 1.055) ** 2.4], dtype=np.float32
        )
        np.testing.assert_allclose(_darkest_palette_color(palette), expected)

        background = np.full((1, 1, 3), 0.5, dtype=np.float32)
        shadow = np.ones((1, 1), dtype=np.float32)
        result = _apply_wave_shadow(
            background, shadow, 1, _darkest_palette_color(palette)
        )
        np.testing.assert_allclose(
            result[0, 0],
            background[0, 0] * (1 - 0.3 * 0.7 * (1 - expected)),
        )

    def test_palette_roles_use_brightness_and_color_separation(self):
        dark_palette = np.asarray(
            [(20, 20, 20), (70, 70, 70), (240, 20, 20)], dtype=np.float32
        )
        primary, accent, gradient = _classify_palette(dark_palette)
        np.testing.assert_array_equal(primary, dark_palette[0])
        np.testing.assert_array_equal(accent, dark_palette[2])
        np.testing.assert_array_equal(gradient, dark_palette[[1]])

        bright_palette = np.asarray(
            [(150, 150, 150), (205, 190, 185), (250, 245, 240)],
            dtype=np.float32,
        )
        primary, _, _ = _classify_palette(bright_palette)
        np.testing.assert_array_equal(primary, bright_palette[2])

    def test_small_palettes_skip_accent_and_keep_colors_in_gradient(self):
        palette = np.asarray([(40, 50, 60), (220, 110, 30)], dtype=np.float32)
        primary, accent, gradient = _classify_palette(palette)
        np.testing.assert_array_equal(primary, palette[0])
        self.assertIsNone(accent)
        np.testing.assert_array_equal(gradient, palette)

    def test_aberration_colors_use_average_palette_saturation_and_lightness(self):
        palette = np.asarray(
            [
                (30, 30, 30),
                (80, 100, 120),
                (150, 100, 80),
                (180, 210, 220),
                (250, 245, 240),
            ],
            dtype=np.float32,
        )
        hls = [
            colorsys.rgb_to_hls(*(color / 255))
            for color in palette
        ]
        average_lightness = float(np.mean([color[1] for color in hls]))
        average_saturation = float(np.mean([color[2] for color in hls]))
        expected = np.asarray(
            [
                colorsys.hls_to_rgb(hue, average_lightness, average_saturation)
                for hue in (0, 1 / 3, 2 / 3)
            ],
            dtype=np.float32,
        ) * 255
        np.testing.assert_allclose(_create_aberration_colors(palette), expected)

    def test_aberration_is_seeded_additive_and_orientation_aware(self):
        mask = np.zeros((24, 32), dtype=np.float32)
        mask[12:] = 1
        image = np.full((24, 32, 3), 0.3, dtype=np.float32)
        colors = np.asarray(
            [(255, 40, 40), (40, 255, 40), (40, 40, 255)], dtype=np.float32
        )

        first = _apply_aberration(
            image.copy(), mask, colors, 1, np.random.default_rng(42), "horizontal"
        )
        repeat = _apply_aberration(
            image.copy(), mask, colors, 1, np.random.default_rng(42), "horizontal"
        )
        other = _apply_aberration(
            image.copy(), mask, colors, 1, np.random.default_rng(43), "horizontal"
        )
        np.testing.assert_array_equal(first, repeat)
        self.assertGreater(float(np.abs(first - image).max()), 0)
        self.assertGreater(float(np.abs(first - other).max()), 0)
        self.assertTrue(np.all(first >= image))
        np.testing.assert_array_equal(first[:10], image[:10])
        np.testing.assert_array_equal(first[14:], image[14:])

        vertical_mask = np.zeros_like(mask)
        vertical_mask[:, 16:] = 1
        vertical = _apply_aberration(
            image.copy(), vertical_mask, colors, 1, np.random.default_rng(42), "vertical"
        )
        self.assertGreater(float(np.abs(vertical - image).max()), 0)
        np.testing.assert_array_equal(vertical[:, :14], image[:, :14])
        np.testing.assert_array_equal(vertical[:, 18:], image[:, 18:])

    def test_aberration_separation_increases_with_edge_strength(self):
        from unittest.mock import Mock

        image = np.zeros((700, 700, 3), dtype=np.float32)
        mask = np.zeros((700, 700), dtype=np.float32)
        mask[350:] = 1
        colors = np.asarray(
            [(255, 40, 40), (40, 255, 40), (40, 40, 255)], dtype=np.float32
        )

        def fixed_rng():
            rng = Mock()
            rng.permutation.return_value = np.asarray((-1, 0, 1))
            rng.integers.side_effect = lambda low, high: high - 1
            rng.uniform.return_value = 0.15
            return rng

        low_strength = _apply_aberration(
            image, mask, colors, 0.1, fixed_rng(), "horizontal"
        )
        high_strength = _apply_aberration(
            image, mask, colors, 1, fixed_rng(), "horizontal"
        )
        low_rows = np.flatnonzero(np.any(low_strength > 0, axis=(1, 2)))
        high_rows = np.flatnonzero(np.any(high_strength > 0, axis=(1, 2)))

        self.assertLess(high_rows[0], low_rows[0])
        self.assertGreater(high_rows[-1], low_rows[-1])

    def test_glue_layer_mixes_palette_colors_and_supports_small_palettes(self):
        image = np.full((32, 48, 3), 0.35, dtype=np.float32)
        palette = np.asarray(
            [(20, 40, 80), (80, 120, 200), (220, 100, 80), (240, 220, 160)],
            dtype=np.float32,
        )
        options = (2, 0.8, 0.35)
        first = _apply_glue_layer(
            image.copy(), palette, np.random.default_rng(42), *options
        )
        repeat = _apply_glue_layer(
            image.copy(), palette, np.random.default_rng(42), *options
        )
        other = _apply_glue_layer(
            image.copy(), palette, np.random.default_rng(43), *options
        )
        np.testing.assert_array_equal(first, repeat)
        self.assertGreater(float(np.abs(first - image).max()), 0)
        self.assertLessEqual(float(np.abs(first - image).max()), 0.2)
        self.assertGreater(float(np.abs(first - other).max()), 0)
        small_palette = _apply_glue_layer(
            image.copy(), palette[:2], np.random.default_rng(42), *options
        )
        self.assertGreater(float(np.abs(small_palette - image).max()), 0)

    def test_halftone_uses_seeded_dots_and_strength_zero_is_noop(self):
        image = np.full((64, 64, 3), 0.5, dtype=np.float32)
        unchanged = _apply_halftone_dither(
            image, 0, np.random.default_rng(42)
        )
        first = _apply_halftone_dither(
            image, 0.75, np.random.default_rng(42)
        )
        repeat = _apply_halftone_dither(
            image, 0.75, np.random.default_rng(42)
        )
        other = _apply_halftone_dither(
            image, 0.75, np.random.default_rng(43)
        )

        np.testing.assert_array_equal(unchanged, image)
        np.testing.assert_array_equal(first, repeat)
        self.assertGreater(float(np.abs(first - image).max()), 0)
        self.assertGreater(float(np.abs(first - other).max()), 0)
        self.assertGreater(np.unique(first[..., 0]).size, 1)

    def test_film_grain_is_independent_seeded_and_strength_zero_is_noop(self):
        image = np.full((64, 64, 3), 0.5, dtype=np.float32)
        unchanged = _apply_film_grain(image, 0, np.random.default_rng(42))
        first = _apply_film_grain(image, 0.5, np.random.default_rng(42))
        repeat = _apply_film_grain(image, 0.5, np.random.default_rng(42))
        other = _apply_film_grain(image, 0.5, np.random.default_rng(43))

        np.testing.assert_array_equal(unchanged, image)
        np.testing.assert_array_equal(first, repeat)
        self.assertGreater(float(first.std()), 0)
        self.assertGreater(float(np.abs(first - other).max()), 0)

    def test_wave_shape_changes_by_seed_but_repeats_for_the_same_seed(self):
        first = _create_wave_layers(256, 128, np.random.default_rng(10), 0.22, 1)
        repeat = _create_wave_layers(256, 128, np.random.default_rng(10), 0.22, 1)
        other = _create_wave_layers(256, 128, np.random.default_rng(11), 0.22, 1)
        for first_layer, repeat_layer in zip(first, repeat):
            np.testing.assert_array_equal(first_layer, repeat_layer)
        self.assertGreater(float(np.abs(first[0] - other[0]).mean()), 0.02)
        self.assertGreater(float(np.abs(first[1] - other[1]).mean()), 0.005)

    def test_point_blending_does_not_create_dark_gaps(self):
        background = np.full((5, 2, 3), 0.35, dtype=np.float32)
        overlay = np.full((5, 2, 3), 0.6, dtype=np.float32)
        mask = np.array([[0, 0], [0, 0], [0.5, 0.5], [1, 1], [1, 1]], dtype=np.float32)
        image = _screen_blend(background, overlay, mask)
        self.assertTrue(np.all(image >= background))
        np.testing.assert_allclose(image[0, 0], background[0, 0])
        self.assertGreater(float(image[2, 0, 0]), float(background[2, 0, 0]))

    def test_both_layers_use_gradient_palette_with_different_angles(self):
        from unittest.mock import patch

        colors = [(20, 40, 100), (100, 80, 190), (250, 140, 160)]
        _, accent_color, gradient_colors = _classify_palette(
            np.asarray(colors, dtype=np.float32)
        )
        all_gradient_colors = (
            gradient_colors
            if accent_color is None
            else np.concatenate((gradient_colors, accent_color[None, :]), axis=0)
        )
        generated = np.full((8, 16, 3), 0.2, dtype=np.float32)
        with patch(
            "gradient_wallpaper.render._create_point_cloud",
            return_value=generated,
        ) as create_point_cloud:
            render(16, 8, colors, "shared-palette")

        first_call, second_call = create_point_cloud.call_args_list
        np.testing.assert_array_equal(first_call.args[2], second_call.args[2])
        self.assertTrue(
            np.array_equal(first_call.args[2], gradient_colors)
            or np.array_equal(
                first_call.args[2], all_gradient_colors
            )
        )
        self.assertNotEqual(first_call.args[5], second_call.args[5])

    def test_cli_writes_requested_size_and_format(self):
        from gradient_wallpaper.cli import main
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "wallpaper.webp"
            arguments = [
                "gradient-wallpaper",
                "--width", "20",
                "--height", "10",
                "--colors", "#123456", "#abcdef",
                "--color-order", "hue",
                "--cloud-spread", "0.5",
                "--wave-edge-strength", "0.8",
                "--wave-edge", "shadow",
                "--wave-ends", "edge-to-edge",
                "--wave-orientation", "vertical",
                "--wave-side", "left",
                "--seed", "test",
                "--output", str(output),
            ]
            with patch("sys.argv", arguments):
                main()
            with Image.open(output) as image:
                self.assertEqual(image.size, (20, 10))
                self.assertEqual(image.format, "WEBP")

    def test_eval_derives_seeded_settings_in_fixed_order(self):
        from contextlib import redirect_stdout
        from io import StringIO
        from gradient_wallpaper.cli import DEFAULT_SETTINGS, main
        from gradient_wallpaper.seed import encode_seed
        from unittest.mock import patch

        def evaluate(seed):
            output = StringIO()
            with patch(
                "sys.argv",
                ["gradient-wallpaper", "eval", "--seed", seed],
            ), redirect_stdout(output):
                main()
            return output.getvalue()

        complete_seed = encode_seed("inspect", dict(DEFAULT_SETTINGS))
        complete_output = evaluate(complete_seed)
        self.assertIn("Seed settings", complete_output)
        self.assertIn("Wave edge strength", complete_output)
        self.assertIn("Wave edge", complete_output)
        halftone_line = next(
            line for line in complete_output.splitlines()
            if line.startswith("Halftone strength")
        )
        self.assertEqual(halftone_line.split("|", 1)[1].strip(), "0.25")
        self.assertNotIn("<random when used>", complete_output)

        entropy_output = evaluate("unbaked-entropy")
        self.assertIn("Entropy-only seed", entropy_output)
        self.assertEqual(entropy_output, evaluate("unbaked-entropy"))
        self.assertNotIn("<random when used>", entropy_output)
        self.assertEqual(
            next(line for line in entropy_output.splitlines() if line.startswith("Width"))
            .split("|", 1)[1].strip(),
            "1920",
        )
        self.assertEqual(
            next(line for line in entropy_output.splitlines() if line.startswith("Height"))
            .split("|", 1)[1].strip(),
            "1080",
        )
        labels = [
            line.split("|", 1)[0].strip()
            for line in entropy_output.splitlines()
            if " | " in line
        ][1:]
        self.assertEqual(
            labels,
            [
                "Width",
                "Height",
                "Colors",
                "Color order",
                "Wave amplitude",
                "Wave frequency",
                "Wave edge strength",
                "Wave opacity",
                "Wave edge",
                "Wave ends",
                "Wave orientation",
                "Wave side",
                "Wave rotation",
                "Zoom",
                "Offset X",
                "Offset Y",
                "Gradient angle",
                "Fine dither",
                "Cloud spread",
                "Glue points",
                "Glue strength",
                "Glue spread",
                "Halftone strength",
                "Grain strength",
            ],
        )

    def test_cli_generates_and_reports_a_random_seed_when_omitted(self):
        from contextlib import redirect_stdout
        from io import StringIO
        from gradient_wallpaper.cli import main
        from gradient_wallpaper.seed import decode_seed
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "wallpaper.png"
            arguments = [
                "gradient-wallpaper",
                "--width", "20",
                "--height", "10",
                "--output", str(output),
            ]
            result = StringIO()
            with patch("sys.argv", arguments), patch(
                "gradient_wallpaper.cli.secrets.token_hex",
                return_value="0123456789abcdef",
            ), redirect_stdout(result):
                main()
            output_seed = result.getvalue().split("seed: ", 1)[1].strip()
            decoded = decode_seed(output_seed)
            self.assertIsNotNone(decoded)
            entropy, settings = decoded
            self.assertEqual(entropy, "0123456789abcdef")
            self.assertEqual((settings["width"], settings["height"]), (20, 10))
            self.assertGreaterEqual(len(settings["colors"]), 3)
            self.assertLessEqual(len(settings["colors"]), 6)
            self.assertTrue(
                all(len(color) == 7 and color.startswith("#") for color in settings["colors"])
            )
            self.assertNotEqual(settings["colors"], [
                "#173B70", "#7165C8", "#F28A9B", "#FFB36B"
            ])
            self.assertTrue(0 <= settings["wave_amplitude"] <= 0.5)
            self.assertLessEqual(settings["wave_amplitude"], 0.18)
            self.assertTrue(0 <= settings["wave_frequency"] <= 4)
            self.assertTrue(0 <= settings["wave_edge_strength"] <= 1)
            self.assertTrue(0.92 <= settings["wave_opacity"] <= 1)
            self.assertTrue(-15 <= settings["wave_rotation"] <= 15)
            self.assertTrue(0 <= settings["zoom"] <= 0.12)
            self.assertTrue(-0.35 <= settings["offset_x"] <= 0.35)
            self.assertTrue(-0.35 <= settings["offset_y"] <= 0.35)
            self.assertTrue(-360 <= settings["angle"] <= 360)
            self.assertTrue(0 <= settings["dither"] <= 1)
            self.assertTrue(0 <= settings["cloud_spread"] <= 1)
            self.assertIn(settings["glue_points"], (2, 3))
            self.assertTrue(0 <= settings["glue_strength"] <= 0.48)
            self.assertTrue(0.2 <= settings["glue_spread"] <= 0.55)
            self.assertTrue(0 <= settings["halftone_strength"] <= 0.45)
            self.assertTrue(0 <= settings["grain_strength"] <= 0.25)
            self.assertIn(settings["color_order"], ("input", "hue"))
            self.assertEqual(settings["wave_edge"], "auto")
            self.assertEqual(settings["wave_ends"], "auto")
            self.assertEqual(settings["wave_orientation"], "auto")
            self.assertEqual(settings["wave_side"], "auto")

            repeated = StringIO()
            with patch("sys.argv", arguments), patch(
                "gradient_wallpaper.cli.secrets.token_hex",
                return_value="0123456789abcdef",
            ), redirect_stdout(repeated):
                main()
            self.assertEqual(
                repeated.getvalue().split("seed: ", 1)[1].strip(), output_seed
            )

    def test_self_contained_seed_replays_and_accepts_setting_overrides(self):
        from contextlib import redirect_stdout
        from io import StringIO
        from gradient_wallpaper.cli import main
        from gradient_wallpaper.seed import decode_seed
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def invoke(*arguments):
                result = StringIO()
                with patch("sys.argv", ["gradient-wallpaper", *arguments]), redirect_stdout(result):
                    main()
                return result.getvalue().split("seed: ", 1)[1].strip()

            original_seed = invoke(
                "create",
                "--width", "20",
                "--height", "10",
                "--colors", "#123456", "#789abc",
                "--wave-edge", "aberration",
                "--wave-ends", "edge-to-edge",
                "--wave-orientation", "vertical",
                "--wave-side", "left",
                "--wave-rotation", "8",
                "--wave-opacity", "0.4",
                "--zoom", "0.25",
                "--offset-x", "0.5",
                "--offset-y", "-0.25",
                "--glue-points", "3",
                "--glue-strength", "0.48",
                "--glue-spread", "0.4",
                "--halftone-strength", "0.6",
                "--grain-strength", "0.3",
                "--seed", "base-seed",
                "--output", str(root / "original.png"),
            )
            replay_seed = invoke(
                "--seed", original_seed,
                "--output", str(root / "replay.png"),
            )
            with Image.open(root / "original.png") as original, Image.open(
                root / "replay.png"
            ) as replay:
                np.testing.assert_array_equal(np.asarray(original), np.asarray(replay))
            self.assertEqual(replay_seed, original_seed)
            _, original_settings = decode_seed(original_seed)
            self.assertEqual(original_settings["glue_points"], 3)
            self.assertEqual(original_settings["glue_strength"], 0.48)
            self.assertEqual(original_settings["glue_spread"], 0.4)
            self.assertEqual(original_settings["halftone_strength"], 0.6)
            self.assertEqual(original_settings["grain_strength"], 0.3)
            self.assertEqual(original_settings["wave_rotation"], 8)
            self.assertEqual(original_settings["wave_opacity"], 0.4)
            self.assertEqual(original_settings["zoom"], 0.25)
            self.assertEqual(original_settings["offset_x"], 0.5)
            self.assertEqual(original_settings["offset_y"], -0.25)

            updated_seed = invoke(
                "--seed", original_seed,
                "--width", "30",
                "--colors", "#AA0000", "#00BB00",
                "--wave-edge-strength", "0.4",
                "--output", str(root / "updated.png"),
            )
            entropy, updated_settings = decode_seed(updated_seed)
            self.assertEqual(entropy, "base-seed")
            self.assertEqual(updated_settings["width"], 30)
            self.assertEqual(updated_settings["height"], 10)
            self.assertEqual(updated_settings["wave_edge_strength"], 0.4)
            self.assertEqual(updated_settings["colors"], ["#AA0000", "#00BB00"])

            invoke(
                "--seed", updated_seed,
                "--output", str(root / "updated-replay.png"),
            )
            with Image.open(root / "updated.png") as updated, Image.open(
                root / "updated-replay.png"
            ) as replay:
                np.testing.assert_array_equal(np.asarray(updated), np.asarray(replay))


if __name__ == "__main__":
    unittest.main()
