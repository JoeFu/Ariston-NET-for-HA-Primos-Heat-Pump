"""Diagnostics support for Ariston (Settings → Devices → ⋮ → Download diagnostics)."""

from __future__ import annotations

from typing import Any

from ariston import DeviceAttribute

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .coordinator import AristonConfigEntry

TO_REDACT = {
    CONF_USERNAME,
    CONF_PASSWORD,
    DeviceAttribute.GW,
    DeviceAttribute.SN,
    DeviceAttribute.LOC,
    DeviceAttribute.GEOFENCE_CONFIG,
    "gwId",
    "gwSerial",
    "plantName",
    "address",
    "latitude",
    "longitude",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: AristonConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    data = entry.runtime_data
    device = data.device

    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "device": {
            "system_type": device.system_type.name,
            "whe_type": device.whe_type.name,
            "whe_model_type": device.whe_model_type,
            "firmware_version": device.firmware_version,
            "has_metering": device.has_metering,
            "has_dhw": device.has_dhw,
            "dhw_mode_changeable": device.dhw_mode_changeable,
            "zone_numbers": getattr(device, "zone_numbers", None),
            "attributes": async_redact_data(device.attributes, TO_REDACT),
            "features": device.features,
            "custom_features": device.custom_features,
            "data": async_redact_data(device.data, TO_REDACT),
            "plant_settings": getattr(device, "plant_settings", None),
            "menu_items": getattr(device, "menu_items", None),
            "consumptions_settings": getattr(device, "consumptions_settings", None),
            "consumptions_sequences": device.consumptions_sequences,
            "bus_errors": async_redact_data(device.bus_errors, TO_REDACT),
        },
        "coordinators": {
            kind: {
                "update_interval": str(coordinator.update_interval),
                "last_update_success": coordinator.last_update_success,
                "last_exception": str(coordinator.last_exception)
                if coordinator.last_exception
                else None,
            }
            for kind, coordinator in data.coordinators.items()
        },
    }
