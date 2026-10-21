"""Velis "plant settings" the ariston library exposes only partially.

The cloud stores advanced water-heater settings (night window, permanent boost, green
ceiling, ...) under model-specific keys: ``Se...`` for the Lydos Hybrid, ``Slp...`` for
the Nuos Split / Primos. This module maps a model-independent name to the right key and
reads / writes it through the generic plant-settings endpoint.
"""

from __future__ import annotations

from datetime import time
from typing import Any

from ariston.const import SeDeviceSettings, SlpDeviceSettings, WheType

# Keys seen in diagnostics of a Primos 205 (Nuos Split model 11); the library has no
# constants for the Slp night / boost settings.
_SLP_NIGHT_MODE_ON_OFF = "SlpNightModeOnOff"
_SLP_NIGHT_BEGIN = "SlpNightBeginAsMinutes"
_SLP_NIGHT_END = "SlpNightEndAsMinutes"
_SLP_PERMANENT_BOOST_ON_OFF = "SlpPermanentBoostOnOff"

NIGHT_MODE = "night_mode"
NIGHT_BEGIN = "night_begin"
NIGHT_END = "night_end"
PERMANENT_BOOST = "permanent_boost"
MAX_GREEN_TEMPERATURE = "max_green_temperature"

PLANT_SETTING_KEYS: dict[WheType, dict[str, str]] = {
    WheType.LydosHybrid: {
        NIGHT_MODE: SeDeviceSettings.SE_NIGHT_MODE_ON_OFF,
        NIGHT_BEGIN: SeDeviceSettings.SE_NIGHT_BEGIN_AS_MINUTES,
        NIGHT_END: SeDeviceSettings.SE_NIGHT_END_AS_MINUTES,
        PERMANENT_BOOST: SeDeviceSettings.SE_PERMANENT_BOOST_ON_OFF,
        MAX_GREEN_TEMPERATURE: SeDeviceSettings.SE_MAX_GREEN_SETPOINT_TEMPERATURE,
    },
    WheType.NuosSplit: {
        NIGHT_MODE: _SLP_NIGHT_MODE_ON_OFF,
        NIGHT_BEGIN: _SLP_NIGHT_BEGIN,
        NIGHT_END: _SLP_NIGHT_END,
        PERMANENT_BOOST: _SLP_PERMANENT_BOOST_ON_OFF,
        MAX_GREEN_TEMPERATURE: SlpDeviceSettings.SLP_MAX_GREEN_TEMPERATURE,
    },
}


def plant_setting_key(device: Any, name: str) -> str | None:
    """Return the cloud key for a setting on this device, or None if the model lacks it."""
    return PLANT_SETTING_KEYS.get(device.whe_type, {}).get(name)


def get_plant_setting(device: Any, name: str) -> Any:
    """Return the cached value of a setting, or None when the cloud did not send it."""
    key = plant_setting_key(device, name)
    if key is None:
        return None
    return getattr(device, "plant_settings", {}).get(key)


def has_plant_setting(device: Any, name: str) -> bool:
    """Return True when the cloud reported this setting for the device."""
    key = plant_setting_key(device, name)
    return key is not None and key in getattr(device, "plant_settings", {})


async def async_set_plant_setting(device: Any, name: str, value: Any) -> None:
    """Write a setting through the generic plant-settings endpoint and cache it."""
    key = plant_setting_key(device, name)
    if key is None:
        raise ValueError(f"{device.whe_type.name} has no setting {name}")
    await device.api.async_set_velis_plant_setting(
        device.plant_data, device.gateway, key, value, device.plant_settings.get(key)
    )
    device.plant_settings[key] = value


# Despite the "AsMinutes" suffix the cloud encodes the night window as hour * 256 + minute
# (23:00 -> 5888, 06:00 -> 1536), which is what the Ariston web portal shows.


def decode_clock(value: Any) -> time | None:
    """Turn a cloud clock value into a time of day."""
    try:
        raw = int(value)
    except (TypeError, ValueError):
        return None
    hour, minute = divmod(raw, 256)
    if not (0 <= hour < 24 and 0 <= minute < 60):
        return None
    return time(hour=hour, minute=minute)


def encode_clock(value: time) -> int:
    """Turn a time of day into the cloud's clock value."""
    return value.hour * 256 + value.minute
