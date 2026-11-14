from __future__ import annotations

import base64
import binascii
import json
from typing import TypedDict, cast

_SEED_VERSION = 8
_PREVIOUS_SEED_VERSIONS = {3, 4, 5, 6, 7}


class SeedSettings(TypedDict):
    width: int
    height: int
    colors: list[str]
    color_order: str
    wave_amplitude: float
    wave_frequency: float
    wave_edge_strength: float
    wave_opacity: float
    wave_edge: str
    wave_ends: str
    wave_orientation: str
    wave_side: str
    wave_rotation: float
    zoom: float
    offset_x: float
    offset_y: float
    angle: float
    dither: float
    cloud_spread: float
    glue_points: int
    glue_strength: float
    glue_spread: float
    halftone_strength: float
    grain_strength: float


_SETTING_KEYS = frozenset(SeedSettings.__annotations__)
_VERSION_7_SETTING_KEYS = (
    (_SETTING_KEYS - {"wave_edge_strength"}) | {"wave_depth"}
)
_VERSION_6_SETTING_KEYS = (
    (_VERSION_7_SETTING_KEYS - {"wave_edge"}) | {"wave_mode", "glue_colors"}
)
_LEGACY_CROP_SETTING_KEYS = (
    _VERSION_6_SETTING_KEYS - {"offset_x", "offset_y"}
) | {"crop_x", "crop_y"}
_VERSION_5_SETTING_KEYS = _LEGACY_CROP_SETTING_KEYS
_VERSION_4_SETTING_KEYS = _VERSION_5_SETTING_KEYS - {"wave_opacity"}
_VERSION_3_SETTING_KEYS = _VERSION_4_SETTING_KEYS - {
    "wave_rotation",
    "zoom",
    "crop_x",
    "crop_y",
}


def encode_seed(entropy: str, settings: SeedSettings) -> str:
    payload = {
        "version": _SEED_VERSION,
        "entropy": entropy,
        "settings": settings,
    }
    data = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    encoded = base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")
    return encoded


def decode_seed(value: str) -> tuple[str, SeedSettings] | None:
    try:
        padded = value + "=" * (-len(value) % 4)
        data = base64.b64decode(padded, altchars=b"-_", validate=True)
        payload = json.loads(data.decode("utf-8"))
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError):
        return None

    if not isinstance(payload, dict):
        return None
    version = payload.get("version")
    if (
        not isinstance(version, int)
        or isinstance(version, bool)
        or (
            version != _SEED_VERSION
            and version not in _PREVIOUS_SEED_VERSIONS
        )
    ):
        return None
    expected_keys = {
        3: _VERSION_3_SETTING_KEYS,
        4: _VERSION_4_SETTING_KEYS,
        5: _VERSION_5_SETTING_KEYS,
        6: _VERSION_6_SETTING_KEYS,
        7: _VERSION_7_SETTING_KEYS,
        _SEED_VERSION: _SETTING_KEYS,
    }[version]
    if (
        not isinstance(payload.get("entropy"), str)
        or not isinstance(payload.get("settings"), dict)
        or frozenset(payload["settings"]) != expected_keys
    ):
        raise ValueError("unsupported or incomplete self-contained seed")

    settings = payload["settings"]
    if version == 3:
        settings = {
            **settings,
            "wave_rotation": 0.0,
            "zoom": 0.0,
            "offset_x": 0.0,
            "offset_y": 0.0,
        }
    elif version in {4, 5}:
        old_zoom = settings["zoom"]
        normalized_zoom = (
            old_zoom - 1
            if isinstance(old_zoom, (int, float))
            and not isinstance(old_zoom, bool)
            else old_zoom
        )
        settings = {
            **{
                key: value
                for key, value in settings.items()
                if key not in {"crop_x", "crop_y"}
            },
            "zoom": normalized_zoom,
            "offset_x": settings["crop_x"],
            "offset_y": settings["crop_y"],
        }
    if version in {3, 4}:
        settings = {**settings, "wave_opacity": 1.0}
    if version <= 6:
        settings = {**settings}
        old_wave_edge = settings.pop("wave_mode")
        settings["wave_edge"] = (
            "aberration"
            if old_wave_edge == "chromatic-aberration"
            else old_wave_edge
        )
        settings.pop("glue_colors")
        old_cloud_spread = settings["cloud_spread"]
        if (
            isinstance(old_cloud_spread, (int, float))
            and not isinstance(old_cloud_spread, bool)
        ):
            settings["cloud_spread"] = (old_cloud_spread - 0.03) / 0.47
        old_glue_strength = settings["glue_strength"]
        if (
            isinstance(old_glue_strength, (int, float))
            and not isinstance(old_glue_strength, bool)
        ):
            settings["glue_strength"] = old_glue_strength / 0.25
    if version != _SEED_VERSION:
        settings = {**settings}
        settings["wave_edge_strength"] = settings.pop("wave_depth")
    if (
        not isinstance(settings["width"], int)
        or isinstance(settings["width"], bool)
        or not isinstance(settings["height"], int)
        or isinstance(settings["height"], bool)
        or not isinstance(settings["colors"], list)
        or not all(isinstance(color, str) for color in settings["colors"])
        or not all(
            isinstance(settings[key], str)
            for key in (
                "color_order",
                "wave_edge",
                "wave_ends",
                "wave_orientation",
                "wave_side",
            )
        )
        or not all(
            isinstance(settings[key], (int, float))
            and not isinstance(settings[key], bool)
            for key in (
                "wave_amplitude",
                "wave_frequency",
                "wave_rotation",
                "zoom",
                "offset_x",
                "offset_y",
                "wave_edge_strength",
                "wave_opacity",
                "angle",
                "dither",
                "cloud_spread",
                "glue_strength",
                "glue_spread",
                "halftone_strength",
                "grain_strength",
            )
        )
        or not isinstance(settings["glue_points"], int)
        or isinstance(settings["glue_points"], bool)
    ):
        raise ValueError("invalid settings in self-contained seed")

    return payload["entropy"], cast(SeedSettings, settings)
