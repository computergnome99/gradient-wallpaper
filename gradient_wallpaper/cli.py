from __future__ import annotations

import argparse
import colorsys
import random
import secrets
import sys
from pathlib import Path

from .render import order_colors, parse_color, render, resolve_wave_options
from .seed import SeedSettings, decode_seed, encode_seed

DEFAULT_COLORS = ["#173B70", "#7165C8", "#F28A9B", "#FFB36B"]
DEFAULT_SETTINGS: SeedSettings = {
    "width": 1920,
    "height": 1080,
    "colors": DEFAULT_COLORS,
    "color_order": "input",
    "wave_amplitude": 0.22,
    "wave_frequency": 1.0,
    "wave_depth": 0.75,
    "wave_opacity": 1.0,
    "wave_mode": "auto",
    "wave_ends": "auto",
    "wave_orientation": "auto",
    "wave_side": "auto",
    "wave_rotation": 0.0,
    "zoom": 0.0,
    "offset_x": 0.0,
    "offset_y": 0.0,
    "angle": 20.0,
    "dither": 0.5,
    "cloud_spread": 0.18,
    "glue_points": 2,
    "glue_colors": 2,
    "glue_strength": 0.07,
    "glue_spread": 0.35,
    "halftone_strength": 0.25,
    "grain_strength": 0.1,
}


def _default_settings() -> SeedSettings:
    return {**DEFAULT_SETTINGS, "colors": list(DEFAULT_COLORS)}


def _random_palette(rng: random.Random, minimum_count: int = 3) -> list[str]:
    count = rng.randint(minimum_count, 6)
    base_hue = rng.random()
    scheme = rng.choice(("analogous", "complementary", "triadic"))
    if scheme == "analogous":
        hues = [
            (base_hue + offset) % 1
            for offset in (
                (index / max(1, count - 1) - 0.5) * 0.16
                for index in range(count)
            )
        ]
    elif scheme == "complementary":
        first_count = (count + 1) // 2
        hues = [
            (base_hue + (index / max(1, first_count - 1) - 0.5) * 0.08) % 1
            for index in range(first_count)
        ]
        second_count = count - first_count
        hues.extend(
            (
                base_hue
                + 0.5
                + (index / max(1, second_count - 1) - 0.5) * 0.08
            )
            % 1
            for index in range(second_count)
        )
    else:
        hues = [
            (base_hue + index / 3 + rng.uniform(-0.025, 0.025)) % 1
            for index in range(count)
        ]
    rng.shuffle(hues)

    neutral_index = rng.randrange(count)
    colors = []
    for index, hue in enumerate(hues):
        saturation = (
            rng.uniform(0.06, 0.22)
            if index == neutral_index
            else rng.uniform(0.45, 0.88)
        )
        lightness = rng.uniform(0.28, 0.78)
        red, green, blue = colorsys.hls_to_rgb(hue, lightness, saturation)
        colors.append(
            "#{:02X}{:02X}{:02X}".format(
                round(red * 255), round(green * 255), round(blue * 255)
            )
        )
    return colors


def _randomize_missing_settings(
    settings: SeedSettings, entropy: str, args: argparse.Namespace
) -> None:
    rng = random.Random(int.from_bytes(entropy.encode("utf-8"), "little"))
    if args.colors is None:
        settings["colors"] = _random_palette(
            rng, minimum_count=5 if args.wave_mode == "chromatic-aberration" else 3
        )
    if args.color_order is None:
        settings["color_order"] = rng.choice(("input", "hue"))
    if args.wave_amplitude is None:
        settings["wave_amplitude"] = 0.06 + 0.12 * rng.random() ** 0.75
    if args.wave_frequency is None:
        settings["wave_frequency"] = 1.5 + 2.5 * rng.random() ** 0.75
    if args.wave_depth is None:
        settings["wave_depth"] = rng.uniform(0, 1)
    if args.angle is None:
        settings["angle"] = rng.uniform(-360, 360)
    if args.dither is None:
        settings["dither"] = rng.uniform(0, 1)
    if args.cloud_spread is None:
        settings["cloud_spread"] = 0.12 + 0.38 * rng.random() ** 0.75
    if args.glue_points is None:
        settings["glue_points"] = rng.randint(2, 3)
    if args.glue_colors is None:
        settings["glue_colors"] = rng.randint(1, 2)
    if args.glue_strength is None:
        settings["glue_strength"] = 0.12 * rng.random() ** 2
    if args.glue_spread is None:
        settings["glue_spread"] = rng.uniform(0.2, 0.55)
    if args.halftone_strength is None:
        settings["halftone_strength"] = 0.45 * rng.random() ** 2
    if args.grain_strength is None:
        settings["grain_strength"] = 0.25 * rng.random() ** 2
    if args.wave_rotation is None:
        settings["wave_rotation"] = rng.uniform(-15, 15)
    if args.wave_opacity is None:
        settings["wave_opacity"] = 0.92 + 0.08 * rng.random() ** 0.25
    if args.zoom is None:
        settings["zoom"] = 0.12 * rng.random() ** 3
    if args.offset_x is None:
        settings["offset_x"] = rng.uniform(-0.35, 0.35)
    if args.offset_y is None:
        settings["offset_y"] = rng.uniform(-0.35, 0.35)


def positive_integer(value: str) -> int:
    try:
        number = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be an integer") from error
    if number < 1:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return number


def non_negative_integer(value: str) -> int:
    try:
        number = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be an integer") from error
    if number < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return number


def bounded_float(minimum: float, maximum: float):
    def parse(value: str) -> float:
        try:
            number = float(value)
        except ValueError as error:
            raise argparse.ArgumentTypeError("must be a number") from error
        if not minimum <= number <= maximum:
            raise argparse.ArgumentTypeError(
                f"must be between {minimum:g} and {maximum:g}"
            )
        return number

    return parse


def _add_create_arguments(parser: argparse.ArgumentParser) -> None:
    parser.description = (
        "Generate a gradient wallpaper. A self-contained seed restores its "
        "colors and settings; explicit options override the seed."
    )
    parser.epilog = (
        "The CLI prints a self-contained seed containing the render settings, "
        "colors, and procedural entropy. Re-run with only --seed to reproduce "
        "the image. If options are also supplied, they override stored values "
        "and the CLI prints an updated seed. Output path and file format are "
        "not stored in the seed. Randomization note: without a self-contained "
        "seed, omitted visual settings and colors are randomized from the seed; "
        "dimensions stay 1920x1080 unless specified. The generated seed stores "
        "those choices for replay. Legacy text/numeric seeds remain supported."
    )
    output_group = parser.add_argument_group("Output image")
    output_group.add_argument(
        "-o", "--output", type=Path, default=Path("wallpaper.png"),
        help="output image path (default: wallpaper.png)",
    )
    output_group.add_argument(
        "--width", type=positive_integer,
        help="image width in pixels (default: 1920)",
    )
    output_group.add_argument(
        "--height", type=positive_integer,
        help="image height in pixels (default: 1080)",
    )
    output_group.add_argument(
        "--format", choices=("png", "jpeg", "webp"),
        help="output format (otherwise inferred from the file extension)",
    )

    palette_group = parser.add_argument_group("Palette and seed")
    palette_group.add_argument(
        "--colors", nargs="+", metavar="HEX",
        help="gradient stops in #RGB or #RRGGBB notation",
    )
    palette_group.add_argument(
        "--color-order", choices=("input", "hue"),
        help="preserve input order or sort by the shortest HSV hue arc",
    )
    palette_group.add_argument(
        "--seed",
        help=(
            "self-contained seed or entropy-only text; settings can override "
            "stored values in a self-contained seed"
        ),
    )

    wave_group = parser.add_argument_group("Wave")
    wave_group.add_argument(
        "--wave-amplitude", type=bounded_float(0, 0.5),
        help="base wave amplitude, from 0 to 0.5",
    )
    wave_group.add_argument(
        "--wave-frequency", type=bounded_float(0, 20),
        help="base path detail, from 0 to 20",
    )
    wave_group.add_argument(
        "--wave-depth", type=bounded_float(0, 1),
        help="wave effect strength from 0 to 1",
    )
    wave_group.add_argument(
        "--wave-opacity", type=bounded_float(0, 1),
        help="wave visibility from 0 (off) to 1 (full)",
    )
    wave_group.add_argument(
        "--wave-mode",
        choices=("auto", "shadow", "underglow", "chromatic-aberration"),
        help="wave treatment, or automatic selection",
    )
    wave_group.add_argument(
        "--wave-ends",
        choices=("auto", "fade", "edge-to-edge"),
        help="fade wave ends or continue to image edges",
    )
    wave_group.add_argument(
        "--wave-orientation",
        choices=("auto", "horizontal", "vertical"),
        help="wave direction",
    )
    wave_group.add_argument(
        "--wave-side",
        choices=("auto", "left", "right"),
        help="vertical foreground side",
    )
    wave_group.add_argument(
        "--wave-rotation", type=bounded_float(-15, 15),
        help="tilt the wave by -15 to 15 degrees",
    )

    framing_group = parser.add_argument_group("Framing")
    framing_group.add_argument(
        "--zoom", type=bounded_float(0, 1),
        help="overscale then crop the canvas, from 0 (off) to 1 (2x)",
    )
    framing_group.add_argument(
        "--offset-x", type=bounded_float(-1, 1),
        help="horizontal offset in the overscan area (-1 left, 1 right)",
    )
    framing_group.add_argument(
        "--offset-y", type=bounded_float(-1, 1),
        help="vertical offset in the overscan area (-1 top, 1 bottom)",
    )

    gradient_group = parser.add_argument_group("Gradient and blending")
    gradient_group.add_argument(
        "--angle", type=bounded_float(-360, 360),
        help="gradient direction in degrees, from -360 to 360",
    )
    gradient_group.add_argument(
        "--cloud-spread", type=bounded_float(0.03, 0.5),
        help="Gaussian point size/spread, from 0.03 to 0.5",
    )
    gradient_group.add_argument(
        "--glue-points", type=non_negative_integer,
        help="number of faint blending points, from 0 to 8",
    )
    gradient_group.add_argument(
        "--glue-colors", type=int, choices=(1, 2),
        help="number of palette colors used by the blending layer, 1 or 2",
    )
    gradient_group.add_argument(
        "--glue-strength", type=bounded_float(0, 0.25),
        help="blending-layer opacity from 0 to 0.25",
    )
    gradient_group.add_argument(
        "--glue-spread", type=bounded_float(0.1, 0.8),
        help="blending-point size as a fraction of image dimensions",
    )

    effects_group = parser.add_argument_group("Post-effects")
    effects_group.add_argument(
        "--dither", type=bounded_float(0, 1),
        help="dither strength from 0 (off) to 1",
    )
    effects_group.add_argument(
        "--halftone-strength", type=bounded_float(0, 1),
        help="ordered dot-dithering strength from 0 (off) to 1 (strong)",
    )
    effects_group.add_argument(
        "--grain-strength", type=bounded_float(0, 1),
        help="filmic grain strength from 0 (off) to 1 (strong)",
    )


def build_create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gradient-wallpaper create",
        description="Generate a procedural gradient wallpaper.",
    )
    _add_create_arguments(parser)
    return parser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gradient-wallpaper",
        description="Create a wallpaper or evaluate a seed's stored settings.",
    )
    subparsers = parser.add_subparsers(dest="command")
    create_parser = subparsers.add_parser(
        "create",
        help="generate an image (the default command)",
        description="Generate a procedural gradient wallpaper.",
    )
    _add_create_arguments(create_parser)
    eval_parser = subparsers.add_parser(
        "eval",
        help="show settings stored in a seed",
        description=(
            "Inspect settings in a self-contained seed. Entropy-only seeds show "
            "which settings will be randomized when used with create."
        ),
    )
    eval_parser.add_argument(
        "--seed",
        required=True,
        help="self-contained seed or entropy-only text/numeric seed",
    )
    return parser


EVAL_SETTINGS = (
    ("Width", "width"),
    ("Height", "height"),
    ("Colors", "colors"),
    ("Color order", "color_order"),
    ("Wave amplitude", "wave_amplitude"),
    ("Wave frequency", "wave_frequency"),
    ("Wave depth", "wave_depth"),
    ("Wave opacity", "wave_opacity"),
    ("Wave mode", "wave_mode"),
    ("Wave ends", "wave_ends"),
    ("Wave orientation", "wave_orientation"),
    ("Wave side", "wave_side"),
    ("Wave rotation", "wave_rotation"),
    ("Zoom", "zoom"),
    ("Offset X", "offset_x"),
    ("Offset Y", "offset_y"),
    ("Gradient angle", "angle"),
    ("Fine dither", "dither"),
    ("Cloud spread", "cloud_spread"),
    ("Glue points", "glue_points"),
    ("Glue colors", "glue_colors"),
    ("Glue strength", "glue_strength"),
    ("Glue spread", "glue_spread"),
    ("Halftone strength", "halftone_strength"),
    ("Grain strength", "grain_strength"),
)


def _format_setting(value: object) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    if value == "auto":
        return "auto (seeded choice)"
    return str(value)


def _evaluate_seed(seed: str, parser: argparse.ArgumentParser) -> None:
    try:
        decoded_seed = decode_seed(seed)
    except ValueError as error:
        parser.error(str(error))

    if decoded_seed is None:
        entropy = seed
        settings = _default_settings()
        random_args = build_create_parser().parse_args([])
        _randomize_missing_settings(settings, entropy, random_args)
        description = (
            "Entropy-only seed; random settings below are deterministically "
            "derived from this seed."
        )
    else:
        entropy, stored_settings = decoded_seed
        settings = {**stored_settings, "colors": list(stored_settings["colors"])}
        description = (
            "Seed settings; automatic wave options are resolved from the seed."
        )

    try:
        colors = order_colors(
            [parse_color(color) for color in settings["colors"]],
            settings["color_order"],
        )
        (
            settings["wave_mode"],
            settings["wave_ends"],
            settings["wave_orientation"],
            settings["wave_side"],
        ) = resolve_wave_options(
            colors,
            entropy,
            settings["wave_mode"],
            settings["wave_ends"],
            settings["wave_orientation"],
            settings["wave_side"],
        )
    except (TypeError, ValueError) as error:
        parser.error(str(error))

    if settings["wave_orientation"] != "vertical":
        settings["wave_side"] = "n/a (horizontal)"
    values = {
        key: _format_setting(settings[key])
        for _, key in EVAL_SETTINGS
    }

    print(description)
    print(f"{'Setting':<22} | Value")
    print(f"{'-' * 22}-+-{'-' * 32}")
    for label, key in EVAL_SETTINGS:
        print(f"{label:<22} | {values[key]}")


def _create(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:

    try:
        decoded_seed = decode_seed(args.seed) if args.seed is not None else None
    except ValueError as error:
        parser.error(str(error))

    if decoded_seed is None:
        entropy = args.seed if args.seed is not None else secrets.token_hex(8)
        settings = _default_settings()
        _randomize_missing_settings(settings, entropy, args)
    else:
        entropy, stored_settings = decoded_seed
        settings = {**stored_settings, "colors": list(stored_settings["colors"])}

    if args.width is not None:
        settings["width"] = args.width
    if args.height is not None:
        settings["height"] = args.height
    if args.colors is not None:
        try:
            settings["colors"] = [
                "#" + "".join(f"{channel:02X}" for channel in parse_color(color))
                for color in args.colors
            ]
        except ValueError as error:
            parser.error(str(error))
    if args.color_order is not None:
        settings["color_order"] = args.color_order
    for argument, setting in (
        ("wave_amplitude", "wave_amplitude"),
        ("wave_frequency", "wave_frequency"),
        ("wave_depth", "wave_depth"),
        ("wave_opacity", "wave_opacity"),
        ("wave_mode", "wave_mode"),
        ("wave_ends", "wave_ends"),
        ("wave_orientation", "wave_orientation"),
        ("wave_side", "wave_side"),
        ("wave_rotation", "wave_rotation"),
        ("zoom", "zoom"),
        ("offset_x", "offset_x"),
        ("offset_y", "offset_y"),
        ("angle", "angle"),
        ("dither", "dither"),
        ("cloud_spread", "cloud_spread"),
        ("glue_points", "glue_points"),
        ("glue_colors", "glue_colors"),
        ("glue_strength", "glue_strength"),
        ("glue_spread", "glue_spread"),
        ("halftone_strength", "halftone_strength"),
        ("grain_strength", "grain_strength"),
    ):
        value = getattr(args, argument)
        if value is not None:
            settings[setting] = value

    try:
        settings["width"] = positive_integer(str(settings["width"]))
        settings["height"] = positive_integer(str(settings["height"]))
        settings["wave_amplitude"] = bounded_float(0, 0.5)(
            str(settings["wave_amplitude"])
        )
        settings["wave_frequency"] = bounded_float(0, 20)(
            str(settings["wave_frequency"])
        )
        settings["wave_rotation"] = bounded_float(-15, 15)(
            str(settings["wave_rotation"])
        )
        settings["zoom"] = bounded_float(0, 1)(str(settings["zoom"]))
        settings["offset_x"] = bounded_float(-1, 1)(
            str(settings["offset_x"])
        )
        settings["offset_y"] = bounded_float(-1, 1)(
            str(settings["offset_y"])
        )
        settings["wave_depth"] = bounded_float(0, 1)(
            str(settings["wave_depth"])
        )
        settings["wave_opacity"] = bounded_float(0, 1)(
            str(settings["wave_opacity"])
        )
        settings["angle"] = bounded_float(-360, 360)(str(settings["angle"]))
        settings["dither"] = bounded_float(0, 1)(str(settings["dither"]))
        settings["cloud_spread"] = bounded_float(0.03, 0.5)(
            str(settings["cloud_spread"])
        )
        settings["glue_points"] = non_negative_integer(
            str(settings["glue_points"])
        )
        settings["glue_strength"] = bounded_float(0, 0.25)(
            str(settings["glue_strength"])
        )
        settings["glue_spread"] = bounded_float(0.1, 0.8)(
            str(settings["glue_spread"])
        )
        settings["halftone_strength"] = bounded_float(0, 1)(
            str(settings["halftone_strength"])
        )
        settings["grain_strength"] = bounded_float(0, 1)(
            str(settings["grain_strength"])
        )
    except argparse.ArgumentTypeError as error:
        parser.error(f"invalid setting in seed: {error}")

    if settings["glue_points"] > 8:
        parser.error("glue-points must be between 0 and 8")

    valid_choices = {
        "color_order": {"input", "hue"},
        "wave_mode": {"auto", "shadow", "underglow", "chromatic-aberration"},
        "wave_ends": {"auto", "fade", "edge-to-edge"},
        "wave_orientation": {"auto", "horizontal", "vertical"},
        "wave_side": {"auto", "left", "right"},
        "glue_colors": {1, 2},
    }
    for key, choices in valid_choices.items():
        if settings[key] not in choices:
            parser.error(f"invalid {key.replace('_', '-')} setting in seed")

    if not settings["colors"]:
        parser.error("at least one color is required")
    try:
        colors = order_colors(
            [parse_color(color) for color in settings["colors"]],
            settings["color_order"],
        )
        image = render(
            width=settings["width"],
            height=settings["height"],
            colors=colors,
            seed=entropy,
            wave_amplitude=settings["wave_amplitude"],
            wave_frequency=settings["wave_frequency"],
            wave_opacity=settings["wave_opacity"],
            angle=settings["angle"],
            dither=settings["dither"],
            cloud_spread=settings["cloud_spread"],
            wave_depth=settings["wave_depth"],
            wave_mode=settings["wave_mode"],
            wave_ends=settings["wave_ends"],
            wave_orientation=settings["wave_orientation"],
            wave_side=settings["wave_side"],
            wave_rotation=settings["wave_rotation"],
            zoom=settings["zoom"],
            offset_x=settings["offset_x"],
            offset_y=settings["offset_y"],
            glue_points=settings["glue_points"],
            glue_colors=settings["glue_colors"],
            glue_strength=settings["glue_strength"],
            glue_spread=settings["glue_spread"],
            halftone_strength=settings["halftone_strength"],
            grain_strength=settings["grain_strength"],
        )
    except (TypeError, ValueError) as error:
        parser.error(str(error))

    seed = encode_seed(entropy, settings)
    output_format = args.format or args.output.suffix.lstrip(".") or "png"
    output_format = {"jpg": "jpeg"}.get(output_format.lower(), output_format.lower())
    if output_format not in {"png", "jpeg", "webp"}:
        parser.error("output extension must be .png, .jpg/.jpeg, or .webp")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    save_options = {"quality": 95, "subsampling": 0} if output_format == "jpeg" else {}
    image.save(args.output, format=output_format.upper(), **save_options)
    print(
        f"Saved {settings['width']}x{settings['height']} {output_format.upper()} image to "
        f"{args.output}\nseed: {seed}"
    )


def main() -> None:
    argv = sys.argv[1:]
    if not argv:
        argv = ["create"]
    elif argv[0] not in {"create", "eval", "-h", "--help"}:
        argv = ["create", *argv]

    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "eval":
        _evaluate_seed(args.seed, parser)
    else:
        _create(args, parser)


if __name__ == "__main__":
    main()
