from __future__ import annotations

import colorsys
import secrets
from collections.abc import Callable

import numpy as np
from PIL import Image, ImageFilter


def _wavy_path(
    x: np.ndarray,
    rng: np.random.Generator,
    baseline: float,
    jitter: float,
    frequency: float,
    tilt_slope: float = 0.0,
) -> np.ndarray:
    point_count = max(4, min(20, round(4 + frequency)))
    points = baseline + rng.normal(0, jitter, size=point_count)
    if tilt_slope:
        point_positions = np.linspace(0, 1, point_count, dtype=np.float32)
        points += tilt_slope * (point_positions - 0.5)
    points = np.clip(points, 0.04, 0.96).astype(np.float32)
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
    wave_rotation: float = 0.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Create a wave mask, a crest highlight, and an inner edge shadow."""
    if wave_ends == "edge-to-edge":
        wave_ends = "full"
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
            wave_rotation=wave_rotation,
        )
        return tuple(layer.T for layer in layers)
    if orientation != "horizontal":
        raise ValueError(f"unknown wave orientation {orientation!r}")
    if wave_ends not in {"fade", "full"}:
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
        float(np.tan(np.deg2rad(wave_rotation)) * width / height),
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

    fade_profile = edge.max(axis=normal_axis, keepdims=True)
    fade_profile /= max(float(fade_profile.max()), 1e-6)
    blur_radius = max(1.0, min(mask.shape) * 0.04)
    edge_image = Image.fromarray(np.uint8(edge * 255))
    blurred = edge_image.filter(ImageFilter.GaussianBlur(blur_radius))
    glow = np.asarray(blurred, dtype=np.float32) / 255
    glow *= (1 - mask) * fade_profile
    glow_peak = float(glow.max())
    if glow_peak <= 1e-6:
        return np.zeros_like(mask)
    return glow / glow_peak


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


def _create_aberration_colors(colors: np.ndarray) -> np.ndarray:
    if not len(colors):
        raise ValueError("at least one palette color is required")

    hls = np.asarray(
        [colorsys.rgb_to_hls(*(color / 255)) for color in colors],
        dtype=np.float32,
    )
    average_lightness = float(hls[:, 1].mean())
    average_saturation = float(hls[:, 2].mean())
    return np.asarray(
        [
            colorsys.hls_to_rgb(hue, average_lightness, average_saturation)
            for hue in (0, 1 / 3, 2 / 3)
        ],
        dtype=np.float32,
    ) * 255


def _create_point_cloud(
    width: int,
    height: int,
    colors: np.ndarray,
    rng: np.random.Generator,
    cloud_spread: float,
    angle: float,
    progress_callback: Callable[[float], None] | None = None,
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
    total_points = len(linear_colors) * point_count
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
        for point_index, center in enumerate(centers):
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
            if progress_callback is not None:
                completed = color_index * point_count + point_index + 1
                progress_callback(completed / total_points)

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
    softened_depth = depth * (1 - 0.3 * depth)
    strength = (shadow * softened_depth * 0.3)[..., None]
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


def _apply_aberration(
    image: np.ndarray,
    mask: np.ndarray,
    colors: np.ndarray,
    depth: float,
    rng: np.random.Generator,
    orientation: str,
) -> np.ndarray:
    if len(colors) != 3 or depth == 0:
        return image

    edge_axis = 0 if orientation == "horizontal" else 1
    if mask.shape[edge_axis] < 2:
        return image

    edge = np.abs(np.gradient(mask, axis=edge_axis))
    peak = float(edge.max())
    if peak <= 1e-6:
        return image
    edge /= peak

    separation_scale = 1 + 0.35 * depth
    max_offset = max(
        1,
        min(8, round(min(image.shape[:2]) * 0.006 * separation_scale)),
    )
    directions = rng.permutation((-1, 0, 1))
    contribution = np.zeros_like(image)
    for color, direction in zip(colors, directions):
        offset = int(rng.integers(1, max_offset + 1))
        shifted_edge = np.zeros_like(edge)
        if direction == 0:
            shifted_edge = edge
        elif direction < 0:
            destination = [slice(None), slice(None)]
            source = [slice(None), slice(None)]
            destination[edge_axis] = slice(None, -offset)
            source[edge_axis] = slice(offset, None)
            shifted_edge[tuple(destination)] = edge[tuple(source)]
        else:
            destination = [slice(None), slice(None)]
            source = [slice(None), slice(None)]
            destination[edge_axis] = slice(offset, None)
            source[edge_axis] = slice(None, -offset)
            shifted_edge[tuple(destination)] = edge[tuple(source)]

        strength = float(rng.uniform(0.1, 0.18)) * depth
        linear_color = _srgb_to_linear(color[None, :])[0]
        contribution += (shifted_edge * strength)[..., None] * linear_color
    return np.clip(image + contribution, 0, 1)


def _apply_glue_layer(
    image: np.ndarray,
    colors: np.ndarray,
    rng: np.random.Generator,
    point_count: int,
    strength: float,
    spread: float,
    progress_callback: Callable[[float], None] | None = None,
) -> np.ndarray:
    unique_colors = np.unique(colors, axis=0)
    if point_count == 0 or strength == 0:
        return image

    linear_colors = _srgb_to_linear(unique_colors)
    mixed_colors = rng.dirichlet(
        np.ones(len(linear_colors), dtype=np.float32), size=point_count
    ) @ linear_colors
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
            np.exp(-0.5 * distance) * strength * 0.25 * rng.uniform(0.7, 1.0)
        )[..., None]
        color = mixed_colors[point_index]
        result = result * (1 - alpha) + color * alpha
        if progress_callback is not None:
            progress_callback((point_index + 1) / point_count)
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


def _apply_fine_dither(
    image: np.ndarray,
    strength: float,
    rng: np.random.Generator,
) -> np.ndarray:
    if strength == 0:
        return image
    noise_strength = strength * (1.25 + 2.25 * strength**2)
    noise = rng.normal(
        0, noise_strength / 255, size=(*image.shape[:2], 1)
    ).astype(image.dtype, copy=False)
    return image + noise


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
    wave_edge: str = "auto",
    wave_ends: str = "auto",
    wave_orientation: str = "auto",
    wave_side: str = "auto",
) -> tuple[str, str, str, str]:
    """Resolve seeded automatic wave options to their effective values."""
    if wave_edge not in {"auto", "shadow", "underglow", "aberration"}:
        raise ValueError(f"unknown wave edge {wave_edge!r}")
    if wave_ends == "edge-to-edge":
        wave_ends = "full"
    if wave_ends not in {"auto", "fade", "full"}:
        raise ValueError(f"unknown wave ends style {wave_ends!r}")
    if wave_orientation not in {"auto", "horizontal", "vertical"}:
        raise ValueError(f"unknown wave orientation {wave_orientation!r}")
    if wave_side not in {"auto", "start", "end"}:
        raise ValueError(f"unknown wave side {wave_side!r}")

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
        else ("fade", "full")[int(ends_rng.integers(0, 2))]
    )
    selected_orientation = (
        wave_orientation
        if wave_orientation != "auto"
        else ("horizontal", "vertical")[int(orientation_rng.integers(0, 2))]
    )
    selected_side = (
        wave_side
        if wave_side != "auto"
        else ("start", "end")[int(side_rng.integers(0, 2))]
        if selected_orientation == "vertical"
        else "end"
    )
    mode_options = ["shadow", "aberration"]
    if accent_color is not None:
        mode_options.append("underglow")
    if wave_edge != "auto" and wave_edge not in mode_options:
        if wave_edge == "underglow":
            raise ValueError("underglow mode requires a suitable accent color")
        raise ValueError(f"unknown or unavailable wave edge {wave_edge!r}")
    selected_edge = (
        mode_options[int(mode_rng.integers(0, len(mode_options)))]
        if wave_edge == "auto"
        else wave_edge
    )
    return selected_edge, selected_ends, selected_orientation, selected_side


def render(
    width: int,
    height: int,
    colors: list[tuple[int, int, int]],
    seed: str | None = None,
    wave_amplitude: float = 0.22,
    wave_frequency: float = 1.0,
    angle: float = 20.0,
    dither: float = 0.5,
    cloud_spread: float = 0.32,
    wave_edge_strength: float = 0.75,
    wave_edge: str = "auto",
    wave_ends: str = "auto",
    wave_orientation: str = "auto",
    wave_side: str = "auto",
    glue_points: int = 2,
    glue_strength: float = 0.28,
    glue_spread: float = 0.35,
    halftone_strength: float = 0.25,
    grain_strength: float = 0.1,
    wave_rotation: float = 0.0,
    zoom: float = 0.0,
    offset_x: float = 0.0,
    offset_y: float = 0.0,
    wave_opacity: float = 1.0,
    progress_callback: Callable[[int, str], None] | None = None,
) -> Image.Image:
    """Render a wave-shaped point-cloud gradient with seeded dithering."""
    if width < 1 or height < 1:
        raise ValueError("width and height must be positive")
    if not colors:
        raise ValueError("at least one color is required")
    if not 0 <= wave_amplitude <= 0.5:
        raise ValueError("wave amplitude must be between 0 and 0.5")
    if not -15 <= wave_rotation <= 15:
        raise ValueError("wave rotation must be between -15 and 15 degrees")
    if not 0 <= zoom <= 1:
        raise ValueError("zoom must be between 0 and 1")
    if not -1 <= offset_x <= 1:
        raise ValueError("offset x must be between -1 and 1")
    if not -1 <= offset_y <= 1:
        raise ValueError("offset y must be between -1 and 1")
    if not 0 <= dither <= 1:
        raise ValueError("dither must be between 0 and 1")
    if not 0 <= cloud_spread <= 1:
        raise ValueError("cloud spread must be between 0 and 1")
    if not 0 <= wave_edge_strength <= 1:
        raise ValueError("wave edge strength must be between 0 and 1")
    if not 0 <= wave_opacity <= 1:
        raise ValueError("wave opacity must be between 0 and 1")
    if not 0 <= glue_points <= 8:
        raise ValueError("glue point count must be between 0 and 8")
    if not 0 <= glue_strength <= 1:
        raise ValueError("glue strength must be between 0 and 1")
    if not 0.1 <= glue_spread <= 0.8:
        raise ValueError("glue spread must be between 0.1 and 0.8")
    if not 0 <= halftone_strength <= 1:
        raise ValueError("halftone strength must be between 0 and 1")
    if not 0 <= grain_strength <= 1:
        raise ValueError("grain strength must be between 0 and 1")
    if seed is None:
        seed = secrets.token_hex(8)

    def report_progress(percent: int, phase: str) -> None:
        if progress_callback is not None:
            progress_callback(percent, phase)

    def stage_progress(
        start: int, end: int, phase: str
    ) -> Callable[[float], None] | None:
        if progress_callback is None:
            return None
        return lambda fraction: report_progress(
            round(start + (end - start) * fraction), phase
        )

    report_progress(0, "Preparing wave")
    output_width, output_height = width, height
    overscale = 1 + zoom
    canvas_width = max(width, int(np.ceil(width * overscale)))
    canvas_height = max(height, int(np.ceil(height * overscale)))
    seed_value = int.from_bytes(seed.encode("utf-8"), "little", signed=False)
    rng = np.random.default_rng(seed_value)
    glue_rng = np.random.default_rng(seed_value ^ 0xA24BAED4963EE407)
    halftone_rng = np.random.default_rng(seed_value ^ 0x9E3779B97F4A7C15)
    grain_rng = np.random.default_rng(seed_value ^ 0x3C6EF372FE94F82A)
    palette = np.asarray(colors, dtype=np.float32)
    primary_color, accent_color, gradient_colors = _classify_palette(palette)
    primary_linear = _srgb_to_linear(primary_color[None, :])[0]

    edge, selected_ends, selected_orientation, selected_side = resolve_wave_options(
        colors,
        seed,
        wave_edge,
        wave_ends,
        wave_orientation,
        wave_side,
    )
    mask, highlight, shadow = _create_wave_layers(
        canvas_width,
        canvas_height,
        rng,
        wave_amplitude,
        wave_frequency,
        orientation=selected_orientation,
        wave_ends=selected_ends,
        foreground_side="top" if selected_side == "start" else "bottom",
        wave_rotation=wave_rotation,
    )
    underglow = _create_wave_underglow_mask(mask, selected_orientation)
    if accent_color is not None:
        gradient_colors = np.concatenate(
            (gradient_colors, accent_color[None, :]), axis=0
        )
    aberration_colors = (
        _create_aberration_colors(palette)
        if edge == "aberration" and wave_opacity > 0
        else None
    )
    effective_cloud_spread = 0.03 + cloud_spread * 0.47

    report_progress(5, "Background gradient")
    background_gradient = _create_point_cloud(
        canvas_width,
        canvas_height,
        gradient_colors,
        rng,
        effective_cloud_spread,
        angle,
        progress_callback=stage_progress(5, 40, "Background gradient"),
    )
    background = primary_linear + (background_gradient - primary_linear) * 0.7
    report_progress(40, "Wave gradient")
    wave = _create_point_cloud(
        canvas_width,
        canvas_height,
        gradient_colors,
        rng,
        effective_cloud_spread,
        angle + rng.uniform(55, 125),
        progress_callback=stage_progress(40, 75, "Wave gradient"),
    )
    report_progress(76, "Compositing wave")
    effective_wave_edge_strength = wave_edge_strength * wave_opacity
    if edge == "shadow" and wave_opacity > 0:
        background = _apply_wave_shadow(
            background,
            shadow,
            effective_wave_edge_strength,
            _darkest_palette_color(palette),
        )
    elif edge == "underglow" and wave_opacity > 0:
        background = _apply_wave_underglow(
            background,
            underglow,
            effective_wave_edge_strength,
            _srgb_to_linear(accent_color[None, :])[0],
        )
    image = _screen_blend(background, wave, mask * wave_opacity)
    if edge == "aberration" and wave_opacity > 0:
        if aberration_colors is None:
            raise RuntimeError("aberration edge has no RGB fringe colors")
        image = _apply_aberration(
            image,
            mask,
            aberration_colors,
            effective_wave_edge_strength,
            rng,
            selected_orientation,
        )
    elif edge in {"shadow", "underglow"} and wave_opacity > 0:
        image = _apply_wave_highlight(
            image,
            highlight,
            effective_wave_edge_strength,
        )
    report_progress(82, "Blending colors")
    image = _apply_glue_layer(
        image,
        palette,
        glue_rng,
        glue_points,
        glue_strength,
        glue_spread,
        progress_callback=stage_progress(82, 90, "Blending colors"),
    )
    report_progress(90, "Post-processing")
    srgb = np.where(
        image <= 0.0031308,
        image * 12.92,
        1.055 * np.maximum(image, 0) ** (1 / 2.4) - 0.055,
    )

    srgb = _apply_fine_dither(srgb, dither, rng)
    srgb = _apply_halftone_dither(srgb, halftone_strength, halftone_rng)
    srgb = _apply_film_grain(srgb, grain_strength, grain_rng)
    pixels = np.clip(srgb * 255, 0, 255).astype(np.uint8)
    image = Image.fromarray(pixels)
    report_progress(97, "Cropping image")
    left = round((canvas_width - output_width) * (offset_x + 1) / 2)
    top = round((canvas_height - output_height) * (offset_y + 1) / 2)
    cropped = image.crop((left, top, left + output_width, top + output_height))
    report_progress(98, "Ready to save")
    return cropped
