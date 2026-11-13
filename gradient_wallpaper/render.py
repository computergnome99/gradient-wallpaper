from __future__ import annotations

import colorsys
import secrets

import numpy as np
from PIL import Image, ImageFilter


def _wavy_path(
    x: np.ndarray,
    rng: np.random.Generator,
    baseline: float,
    jitter: float,
    frequency: float,
) -> np.ndarray:
    point_count = max(4, min(20, round(4 + frequency)))
    points = np.clip(
        baseline + rng.normal(0, jitter, size=point_count), 0.04, 0.96
    ).astype(np.float32)
    scaled_x = x * (point_count - 1)
    segment = np.minimum(scaled_x.astype(np.intp), point_count - 2)
    amount = scaled_x - segment
    p0 = points[np.maximum(segment - 1, 0)]
    p1 = points[segment]
    p2 = points[segment + 1]
    p3 = points[np.minimum(segment + 2, point_count - 1)]
    return 0.5 * (
        2 * p1
        + (-p0 + p2) * amount
        + (2 * p0 - 5 * p1 + 4 * p2 - p3) * amount**2
        + (-p0 + 3 * p1 - 3 * p2 + p3) * amount**3
    )


def _create_wave_layers(
    width: int,
    height: int,
    rng: np.random.Generator,
    wave_amplitude: float,
    wave_frequency: float,
    orientation: str = "horizontal",
    wave_ends: str = "fade",
    foreground_side: str = "bottom",
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Create a wave mask, a crest highlight, and an inner edge shadow."""
    if orientation == "vertical":
        layers = _create_wave_layers(
            height,
            width,
            rng,
            wave_amplitude,
            wave_frequency,
            orientation="horizontal",
            wave_ends=wave_ends,
            foreground_side=foreground_side,
        )
        return tuple(layer.T for layer in layers)
    if orientation != "horizontal":
        raise ValueError(f"unknown wave orientation {orientation!r}")
    if wave_ends not in {"fade", "edge-to-edge"}:
        raise ValueError(f"unknown wave ends style {wave_ends!r}")
    if foreground_side not in {"bottom", "top"}:
        raise ValueError(f"unknown horizontal foreground side {foreground_side!r}")

    x = np.linspace(0, 1, width, dtype=np.float32)[None, :]
    y = np.linspace(0, 1, height, dtype=np.float32)[:, None]

    baseline = float(rng.uniform(0.32, 0.68))
    effective_amplitude = min(0.5, wave_amplitude * rng.uniform(0.65, 1.45))
    effective_frequency = np.clip(
        wave_frequency * rng.uniform(0.5, 2.2), 0, 20
    )
    path = _wavy_path(
        x,
        rng,
        baseline,
        effective_amplitude * rng.uniform(0.7, 1.1),
        float(effective_frequency),
    )
    light_side = int(rng.choice((-1, 1)))
    signed_distance = (y - path) * height
    vertical = np.clip(signed_distance / max(1.0, height * 0.006) + 0.5, 0, 1)
    vertical = vertical * vertical * (3 - 2 * vertical)
    if foreground_side == "top":
        vertical = 1 - vertical

    if wave_ends == "fade":
        end_fade = 0.2
        fade_in = np.clip(x / end_fade, 0, 1)
        fade_out = np.clip((1 - x) / end_fade, 0, 1)
        fade = fade_in**2 * (3 - 2 * fade_in) * fade_out**2 * (3 - 2 * fade_out)
    else:
        fade = np.ones_like(x)
    mask = vertical * fade

    blur_radius = max(0.5, min(width, height) * 0.003)
    mask_image = Image.fromarray(np.uint8(mask * 255))
    blurred = mask_image.filter(ImageFilter.GaussianBlur(blur_radius))
    mask = np.asarray(blurred, dtype=np.float32) / 255 * fade

    path_slope = (
        np.gradient(path[0], x[0]) if width > 1 else np.zeros(width, dtype=np.float32)
    )
    facing_light = np.clip(light_side * path_slope, 0, 1)
    highlight_facing = 0.12 + 0.88 * facing_light
    highlight_width = max(1.0, min(width, height) * 0.003)
    highlight_offset = highlight_width * 0.8
    highlight_distance = (
        signed_distance - highlight_offset
        if foreground_side == "top"
        else signed_distance + highlight_offset
    )
    highlight = np.exp(
        -0.5 * (highlight_distance / highlight_width) ** 2
    ) * fade * highlight_facing

    shadow_offset = max(2, round(min(width, height) * 0.022))
    shifted_mask = np.zeros_like(mask)
    if light_side > 0:
        shifted_mask[:, :-shadow_offset] = mask[:, shadow_offset:]
    else:
        shifted_mask[:, shadow_offset:] = mask[:, :-shadow_offset]
    shadow_blur = max(1.0, min(width, height) * 0.018)
    shadow_image = Image.fromarray(np.uint8(shifted_mask * 255))
    shadow_image = shadow_image.filter(ImageFilter.GaussianBlur(shadow_blur))
    shadow = np.asarray(shadow_image, dtype=np.float32) / 255
    shadow *= (1 - mask) * fade
    return mask, highlight, shadow


def _create_wave_underglow_mask(
    mask: np.ndarray, orientation: str
) -> np.ndarray:
    normal_axis = 0 if orientation == "horizontal" else 1
    if mask.shape[normal_axis] < 2:
        return np.zeros_like(mask)

    edge = np.abs(np.gradient(mask, axis=normal_axis))
    peak = float(edge.max())
    if peak <= 1e-6:
        return np.zeros_like(mask)
    edge /= peak

    blur_radius = max(1.0, min(mask.shape) * 0.012)
    edge_image = Image.fromarray(np.uint8(edge * 255))
    blurred = edge_image.filter(ImageFilter.GaussianBlur(blur_radius))
    return np.asarray(blurred, dtype=np.float32) / 255


def parse_color(value: str) -> tuple[int, int, int]:
    """Parse a six- or three-digit RGB hex color."""
    color = value.removeprefix("#")
    if len(color) == 3:
        color = "".join(component * 2 for component in color)
    if len(color) != 6:
        raise ValueError(f"invalid color {value!r}: expected #RGB or #RRGGBB")
    try:
        return tuple(int(color[index : index + 2], 16) for index in (0, 2, 4))
    except ValueError as error:
        raise ValueError(
            f"invalid color {value!r}: expected #RGB or #RRGGBB"
        ) from error


def order_colors(
    colors: list[tuple[int, int, int]], order: str
) -> list[tuple[int, int, int]]:
    if order == "input" or len(colors) < 2:
        return colors
    if order != "hue":
        raise ValueError(f"unknown color order {order!r}")

    hue_colors = sorted(
        (
            colorsys.rgb_to_hsv(*(component / 255 for component in color))[0],
            index,
            color,
        )
        for index, color in enumerate(colors)
    )
    gaps = [
        (hue_colors[(index + 1) % len(colors)][0] - hue) % 1
        for index, (hue, _, _) in enumerate(hue_colors)
    ]
    widest_gap = int(np.argmax(gaps))
    if gaps[widest_gap] <= 1e-6:
        return [color for _, _, color in hue_colors]
    start = widest_gap + 1
    return [
        color
        for _, _, color in hue_colors[start:] + hue_colors[:start]
    ]


def _srgb_to_linear(colors: np.ndarray) -> np.ndarray:
    srgb = colors / 255
    return np.where(
        srgb <= 0.04045,
        srgb / 12.92,
        ((srgb + 0.055) / 1.055) ** 2.4,
    ).astype(np.float32)


def _darkest_palette_color(colors: np.ndarray) -> np.ndarray:
    linear_colors = _srgb_to_linear(colors)
    luminance = linear_colors @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    return linear_colors[int(np.argmin(luminance))]


def _classify_palette(
    colors: np.ndarray,
) -> tuple[np.ndarray, np.ndarray | None, np.ndarray]:
    linear_colors = _srgb_to_linear(colors)
    luminance = linear_colors @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    saturation = np.array(
        [colorsys.rgb_to_hsv(*(color / 255))[1] for color in colors],
        dtype=np.float32,
    )

    if np.count_nonzero(luminance >= 0.5) > len(colors) / 2:
        primary_index = int(np.argmax(luminance))
    elif np.count_nonzero(luminance < 0.5) > len(colors) / 2:
        primary_index = int(np.argmin(luminance))
    else:
        primary_index = int(np.argmin(saturation))

    remaining = np.array(
        [index for index in range(len(colors)) if index != primary_index],
        dtype=np.intp,
    )
    if len(colors) < 3:
        return colors[primary_index], None, colors

    distance = np.linalg.norm(
        linear_colors[remaining] - linear_colors[primary_index], axis=1
    ) / np.sqrt(3)
    accent_score = np.maximum(saturation[remaining], distance)
    accent_offset = int(np.argmax(accent_score))
    if accent_score[accent_offset] < 0.25:
        return colors[primary_index], None, colors[remaining]

    accent_index = int(remaining[accent_offset])
    gradient_indices = remaining[remaining != accent_index]
    return colors[primary_index], colors[accent_index], colors[gradient_indices]


def _extract_chromatic_colors(
    colors: np.ndarray,
) -> tuple[np.ndarray, np.ndarray | None]:
    if len(colors) < 4:
        return colors, None

    linear_colors = _srgb_to_linear(colors)
    luminance = linear_colors @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    brightest_indices = np.argsort(luminance, kind="stable")[-2:]
    gradient_indices = np.array(
        [index for index in range(len(colors)) if index not in brightest_indices],
        dtype=np.intp,
    )
    return colors[gradient_indices], colors[brightest_indices]


def _create_point_cloud(
    width: int,
    height: int,
    colors: np.ndarray,
    rng: np.random.Generator,
    cloud_spread: float,
    angle: float,
) -> np.ndarray:
    """Splat colored points around a warped color field, blending in linear light."""
    low_width = max(1, (width + 1) // 2)
    low_height = max(1, (height + 1) // 2)
    x = np.linspace(0, 1, low_width, dtype=np.float32)[None, :]
    y = np.linspace(0, 1, low_height, dtype=np.float32)[:, None]

    radians = np.deg2rad(angle)
    dx, dy = np.cos(radians), np.sin(radians)
    position = (
        (x - 0.5) * dx + (y - 0.5) * dy
    ) / (abs(dx) + abs(dy)) + 0.5
    noise_grid = rng.normal(0, 1, size=(5, 5)).astype(np.float32)
    noise = np.asarray(
        Image.fromarray(noise_grid).resize(
            (low_width, low_height), Image.Resampling.BICUBIC
        ),
        dtype=np.float32,
    ).copy()
    noise /= max(float(noise.std()), 1e-6)
    flat_position = np.clip(position + noise * 0.18, 0, 1).ravel()

    if len(colors) == 1:
        base = colors[0]
        colors = np.stack((base * 0.72, base * 0.88 + 255 * 0.12))
    linear_colors = _srgb_to_linear(colors)

    accumulated = np.zeros((low_height, low_width, 3), dtype=np.float32)
    total_weight = np.full((low_height, low_width), 0.02, dtype=np.float32)
    accumulated += linear_colors.mean(axis=0) * 0.02

    point_count = max(2, min(5, 14 // len(colors)))
    band_width = max(0.06, 0.55 / max(1, len(colors) - 1))
    for color_index, color in enumerate(linear_colors):
        target = color_index / max(1, len(colors) - 1)
        candidates = np.flatnonzero(np.abs(flat_position - target) <= band_width)
        if not candidates.size:
            nearest_count = min(point_count, flat_position.size)
            candidates = np.argpartition(
                np.abs(flat_position - target), nearest_count - 1
            )[:nearest_count]
        centers = rng.choice(
            candidates, size=point_count, replace=candidates.size < point_count
        )
        for center in centers:
            center_y, center_x = divmod(int(center), low_width)
            center_x /= max(1, low_width - 1)
            center_y /= max(1, low_height - 1)
            sigma_y = cloud_spread * rng.uniform(0.55, 1.6)
            sigma_x = sigma_y * height / width
            strength = rng.uniform(0.7, 1.3)
            distance = ((x - center_x) / sigma_x) ** 2 + (
                (y - center_y) / sigma_y
            ) ** 2
            weight = np.exp(-0.5 * distance) * strength
            accumulated += weight[..., None] * color
            total_weight += weight

    cloud = accumulated / total_weight[..., None]
    channels = [
        np.asarray(
            Image.fromarray(cloud[..., channel]).resize(
                (width, height), Image.Resampling.BICUBIC
            ),
            dtype=np.float32,
        )
        for channel in range(3)
    ]
    return np.stack(channels, axis=-1)


def _screen_blend(
    background: np.ndarray, overlay: np.ndarray, mask: np.ndarray
) -> np.ndarray:
    """Lighten in linear RGB while ensuring the overlay never darkens the base."""
    contribution = overlay * (mask * 0.34)[..., None]
    return 1 - (1 - background) * (1 - contribution)


def _apply_wave_shadow(
    background: np.ndarray,
    shadow: np.ndarray,
    depth: float,
    shadow_color: np.ndarray,
) -> np.ndarray:
    strength = (shadow * depth * 0.3)[..., None]
    return background * (1 - strength * (1 - shadow_color))


def _apply_wave_underglow(
    image: np.ndarray,
    mask: np.ndarray,
    depth: float,
    color: np.ndarray,
) -> np.ndarray:
    strength = (mask * depth * 0.3)[..., None]
    return np.minimum(image + color * strength, 1)


def _apply_wave_highlight(
    image: np.ndarray,
    highlight: np.ndarray,
    depth: float,
    intensity: float = 1.0,
) -> np.ndarray:
    highlight_color = np.array([1.0, 0.98, 0.92], dtype=np.float32)
    highlight_strength = (
        highlight * depth * 0.24 * intensity
    )[..., None] * highlight_color
    return 1 - (1 - image) * (1 - highlight_strength)


def _apply_chromatic_aberration(
    image: np.ndarray,
    mask: np.ndarray,
    colors: np.ndarray,
    depth: float,
    rng: np.random.Generator,
) -> np.ndarray:
    if len(colors) < 2 or mask.shape[0] < 2 or depth == 0:
        return image

    edge = np.abs(np.gradient(mask, axis=0))
    peak = float(edge.max())
    if peak <= 1e-6:
        return image
    edge /= peak

    max_offset = max(1, min(8, round(min(image.shape[:2]) * 0.006)))
    directions = [-1, 1]
    if rng.integers(0, 2):
        directions.reverse()

    result = image
    for color, direction in zip(colors, directions):
        offset = int(rng.integers(1, max_offset + 1))
        shifted_edge = np.zeros_like(edge)
        if direction < 0:
            shifted_edge[:-offset] = edge[offset:]
        else:
            shifted_edge[offset:] = edge[:-offset]

        strength = float(rng.uniform(0.12, 0.22)) * depth
        alpha = (shifted_edge * strength)[..., None]
        linear_color = _srgb_to_linear(color[None, :])[0]
        result = result * (1 - alpha) + linear_color * alpha
    return result


def _apply_glue_layer(
    image: np.ndarray,
    colors: np.ndarray,
    rng: np.random.Generator,
    point_count: int,
    color_count: int,
    strength: float,
    spread: float,
) -> np.ndarray:
    unique_colors = np.unique(colors, axis=0)
    if len(unique_colors) < 3 or point_count == 0 or strength == 0:
        return image

    color_count = min(color_count, len(unique_colors))
    selected = rng.choice(len(unique_colors), size=color_count, replace=False)
    linear_colors = _srgb_to_linear(unique_colors[selected])
    height, width = image.shape[:2]
    x = np.linspace(0, 1, width, dtype=np.float32)[None, :]
    y = np.linspace(0, 1, height, dtype=np.float32)[:, None]

    result = image
    for point_index in range(point_count):
        center_x = float(rng.uniform(0.1, 0.9))
        center_y = float(rng.uniform(0.1, 0.9))
        sigma_x = spread * rng.uniform(0.8, 1.2)
        sigma_y = spread * rng.uniform(0.8, 1.2)
        distance = ((x - center_x) / sigma_x) ** 2 + (
            (y - center_y) / sigma_y
        ) ** 2
        alpha = (
            np.exp(-0.5 * distance) * strength * rng.uniform(0.7, 1.0)
        )[..., None]
        color = linear_colors[point_index % color_count]
        result = result * (1 - alpha) + color * alpha
    return result


def _apply_halftone_dither(
    image: np.ndarray,
    strength: float,
    rng: np.random.Generator,
) -> np.ndarray:
    if strength == 0:
        return image

    linear = np.where(
        image <= 0.04045,
        image / 12.92,
        ((image + 0.055) / 1.055) ** 2.4,
    ).astype(np.float32)
    luminance = linear @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    level_count = round(64 - strength * 48)
    scaled_luminance = luminance * (level_count - 1)
    lower_level = np.floor(scaled_luminance)
    fraction = scaled_luminance - lower_level

    cell_size = 8
    axis = np.arange(cell_size, dtype=np.float32) - (cell_size - 1) / 2
    distance = np.sqrt(axis[:, None] ** 2 + axis[None, :] ** 2)
    threshold_pattern = distance / distance.max()
    threshold_pattern = np.rot90(
        threshold_pattern, int(rng.integers(0, 4))
    )
    height, width = image.shape[:2]
    offset_y, offset_x = rng.integers(0, cell_size, size=2)
    threshold = threshold_pattern[
        (np.arange(height) + offset_y) % cell_size, :
    ][:, (np.arange(width) + offset_x) % cell_size]

    quantized_luminance = (
        lower_level + (fraction > threshold)
    ) / (level_count - 1)
    quantized_luminance = np.minimum(quantized_luminance, 1)
    maximum_channel = np.max(linear, axis=-1)
    scale = np.divide(
        quantized_luminance,
        luminance,
        out=np.zeros_like(luminance),
        where=luminance > 1e-6,
    )
    scale = np.minimum(
        scale,
        np.divide(
            1,
            maximum_channel,
            out=np.ones_like(maximum_channel),
            where=maximum_channel > 1e-6,
        ),
    )
    quantized_linear = linear * scale[..., None]
    quantized_srgb = np.where(
        quantized_linear <= 0.0031308,
        quantized_linear * 12.92,
        1.055 * np.maximum(quantized_linear, 0) ** (1 / 2.4) - 0.055,
    )
    return image * (1 - strength) + quantized_srgb * strength


def _apply_film_grain(
    image: np.ndarray,
    strength: float,
    rng: np.random.Generator,
) -> np.ndarray:
    if strength == 0:
        return image
    grain = rng.normal(
        0, 0.035 * strength, size=(*image.shape[:2], 1)
    ).astype(np.float32)
    return np.clip(image + grain, 0, 1)


def resolve_wave_options(
    colors: list[tuple[int, int, int]],
    seed: str,
    wave_mode: str = "auto",
    wave_ends: str = "auto",
    wave_orientation: str = "auto",
    wave_side: str = "auto",
) -> tuple[str, str, str, str]:
    """Resolve seeded automatic wave options to their effective values."""
    if wave_mode not in {"auto", "shadow", "underglow", "chromatic-aberration"}:
        raise ValueError(f"unknown wave mode {wave_mode!r}")
    if wave_ends not in {"auto", "fade", "edge-to-edge"}:
        raise ValueError(f"unknown wave ends style {wave_ends!r}")
    if wave_orientation not in {"auto", "horizontal", "vertical"}:
        raise ValueError(f"unknown wave orientation {wave_orientation!r}")
    if wave_side not in {"auto", "left", "right"}:
        raise ValueError(f"unknown vertical wave side {wave_side!r}")
    if wave_orientation == "horizontal" and wave_side != "auto":
        raise ValueError("wave side left/right is only available for vertical waves")

    seed_value = int.from_bytes(seed.encode("utf-8"), "little", signed=False)
    mode_rng = np.random.default_rng(seed_value ^ 0xD1B54A32D192ED03)
    ends_rng = np.random.default_rng(seed_value ^ 0x94D049BB133111EB)
    orientation_rng = np.random.default_rng(seed_value ^ 0xBF58476D1CE4E5B9)
    side_rng = np.random.default_rng(seed_value ^ 0xDB4F0B9175AE2165)
    palette = np.asarray(colors, dtype=np.float32)
    _, accent_color, gradient_colors = _classify_palette(palette)

    selected_ends = (
        wave_ends
        if wave_ends != "auto"
        else ("fade", "edge-to-edge")[int(ends_rng.integers(0, 2))]
    )
    selected_orientation = (
        wave_orientation
        if wave_orientation != "auto"
        else (
            "vertical"
            if wave_side != "auto"
            else ("horizontal", "vertical")[int(orientation_rng.integers(0, 2))]
        )
    )
    selected_side = (
        wave_side
        if wave_side != "auto"
        else ("left", "right")[int(side_rng.integers(0, 2))]
        if selected_orientation == "vertical"
        else "right"
    )
    mode_options = ["shadow"]
    if accent_color is not None:
        mode_options.append("underglow")
    if len(gradient_colors) + (accent_color is not None) >= 4:
        mode_options.append("chromatic-aberration")
    if wave_mode != "auto" and wave_mode not in mode_options:
        if wave_mode == "underglow":
            raise ValueError("underglow mode requires a suitable accent color")
        raise ValueError(
            "chromatic-aberration mode requires at least four non-primary colors"
        )
    selected_mode = (
        mode_options[int(mode_rng.integers(0, len(mode_options)))]
        if wave_mode == "auto"
        else wave_mode
    )
    return selected_mode, selected_ends, selected_orientation, selected_side


def render(
    width: int,
    height: int,
    colors: list[tuple[int, int, int]],
    seed: str | None = None,
    wave_amplitude: float = 0.22,
    wave_frequency: float = 1.0,
    angle: float = 20.0,
    dither: float = 0.5,
    cloud_spread: float = 0.18,
    wave_depth: float = 0.75,
    wave_mode: str = "auto",
    wave_ends: str = "auto",
    wave_orientation: str = "auto",
    wave_side: str = "auto",
    glue_points: int = 2,
    glue_colors: int = 2,
    glue_strength: float = 0.07,
    glue_spread: float = 0.35,
    halftone_strength: float = 0.25,
    grain_strength: float = 0.1,
) -> Image.Image:
    """Render a wave-shaped point-cloud gradient with seeded dithering."""
    if width < 1 or height < 1:
        raise ValueError("width and height must be positive")
    if not colors:
        raise ValueError("at least one color is required")
    if not 0 <= wave_amplitude <= 0.5:
        raise ValueError("wave amplitude must be between 0 and 0.5")
    if not 0 <= dither <= 1:
        raise ValueError("dither must be between 0 and 1")
    if not 0.03 <= cloud_spread <= 0.5:
        raise ValueError("cloud spread must be between 0.03 and 0.5")
    if not 0 <= wave_depth <= 1:
        raise ValueError("wave depth must be between 0 and 1")
    if not 0 <= glue_points <= 8:
        raise ValueError("glue point count must be between 0 and 8")
    if glue_colors not in {1, 2}:
        raise ValueError("glue color count must be 1 or 2")
    if not 0 <= glue_strength <= 0.25:
        raise ValueError("glue strength must be between 0 and 0.25")
    if not 0.1 <= glue_spread <= 0.8:
        raise ValueError("glue spread must be between 0.1 and 0.8")
    if not 0 <= halftone_strength <= 1:
        raise ValueError("halftone strength must be between 0 and 1")
    if not 0 <= grain_strength <= 1:
        raise ValueError("grain strength must be between 0 and 1")
    if seed is None:
        seed = secrets.token_hex(8)
    seed_value = int.from_bytes(seed.encode("utf-8"), "little", signed=False)
    rng = np.random.default_rng(seed_value)
    glue_rng = np.random.default_rng(seed_value ^ 0xA24BAED4963EE407)
    halftone_rng = np.random.default_rng(seed_value ^ 0x9E3779B97F4A7C15)
    grain_rng = np.random.default_rng(seed_value ^ 0x3C6EF372FE94F82A)
    palette = np.asarray(colors, dtype=np.float32)
    primary_color, accent_color, gradient_colors = _classify_palette(palette)
    primary_linear = _srgb_to_linear(primary_color[None, :])[0]

    mode, selected_ends, selected_orientation, selected_side = resolve_wave_options(
        colors,
        seed,
        wave_mode,
        wave_ends,
        wave_orientation,
        wave_side,
    )
    mask, highlight, shadow = _create_wave_layers(
        width,
        height,
        rng,
        wave_amplitude,
        wave_frequency,
        orientation=selected_orientation,
        wave_ends=selected_ends,
        foreground_side=(
            "top" if selected_orientation == "vertical" and selected_side == "left"
            else "bottom"
        ),
    )
    underglow = _create_wave_underglow_mask(mask, selected_orientation)
    aberration_colors = None
    if mode != "underglow" and accent_color is not None:
        gradient_colors = np.concatenate(
            (gradient_colors, accent_color[None, :]), axis=0
        )
    if mode == "chromatic-aberration":
        gradient_colors, aberration_colors = _extract_chromatic_colors(
            gradient_colors
        )

    background_gradient = _create_point_cloud(
        width, height, gradient_colors, rng, cloud_spread, angle
    )
    background = primary_linear + (background_gradient - primary_linear) * 0.7
    wave = _create_point_cloud(
        width,
        height,
        gradient_colors,
        rng,
        cloud_spread,
        angle + rng.uniform(55, 125),
    )
    if mode == "shadow":
        background = _apply_wave_shadow(
            background, shadow, wave_depth, _darkest_palette_color(palette)
        )
    elif mode == "underglow":
        background = _apply_wave_underglow(
            background,
            underglow,
            wave_depth,
            _srgb_to_linear(accent_color[None, :])[0],
        )
    image = _screen_blend(background, wave, mask)
    if mode == "chromatic-aberration":
        if aberration_colors is None:
            raise RuntimeError("chromatic aberration mode has no edge colors")
        image = _apply_chromatic_aberration(
            image, mask, aberration_colors, wave_depth, rng
        )
    elif mode in {"shadow", "underglow"}:
        highlight_intensity = 0.5 if mode == "underglow" else 1.0
        image = _apply_wave_highlight(
            image, highlight, wave_depth, intensity=highlight_intensity
        )
    image = _apply_glue_layer(
        image,
        palette,
        glue_rng,
        glue_points,
        glue_colors,
        glue_strength,
        glue_spread,
    )
    srgb = np.where(
        image <= 0.0031308,
        image * 12.92,
        1.055 * np.maximum(image, 0) ** (1 / 2.4) - 0.055,
    )

    if dither:
        srgb += rng.normal(0, dither * 1.25 / 255, size=(height, width, 1))
    srgb = _apply_halftone_dither(srgb, halftone_strength, halftone_rng)
    srgb = _apply_film_grain(srgb, grain_strength, grain_rng)
    pixels = np.clip(srgb * 255, 0, 255).astype(np.uint8)
    return Image.fromarray(pixels)
