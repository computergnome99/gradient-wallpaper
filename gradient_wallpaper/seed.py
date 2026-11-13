from __future__ import annotations

import base64
import binascii
import json
from typing import TypedDict, cast

_SEED_VERSION = 3


class SeedSettings(TypedDict):
    width: int
    height: int
    colors: list[str]
    color_order: str
    wave_amplitude: float
    wave_frequency: float
    wave_depth: float
    wave_mode: str
    wave_ends: str
    wave_orientation: str
    wave_side: str
    angle: float
    dither: float
    cloud_spread: float
    glue_points: int
    glue_colors: int
    glue_strength: float
    glue_spread: float
    halftone_strength: float
    grain_strength: float


_SETTING_KEYS = frozenset(SeedSettings.__annotations__)


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

    if (
        not isinstance(payload, dict)
        or payload.get("version") != _SEED_VERSION
    ):
        return None
    if (
        not isinstance(payload.get("entropy"), str)
        or not isinstance(payload.get("settings"), dict)
        or frozenset(payload["settings"]) != _SETTING_KEYS
    ):
        raise ValueError("unsupported or incomplete self-contained seed")

    settings = payload["settings"]
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
                "wave_mode",
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
                "wave_depth",
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
        or not isinstance(settings["glue_colors"], int)
        or isinstance(settings["glue_colors"], bool)
    ):
        raise ValueError("invalid settings in self-contained seed")

    return payload["entropy"], cast(SeedSettings, settings)
