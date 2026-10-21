"""Services for the Ariston integration."""

from __future__ import annotations

import logging
from datetime import date

import voluptuous as vol
from ariston.const import SystemType

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN
from .coordinator import AristonConfigEntry

_LOGGER = logging.getLogger(__name__)

SERVICE_SET_ITEM_BY_ID = "set_item_by_id"
SERVICE_CREATE_VACATION = "create_vacation"

ATTR_ITEM_ID = "item_id"
ATTR_ZONE = "zone"
ATTR_VALUE = "value"
ATTR_END_DATE = "end_date"

SET_ITEM_BY_ID_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.string,
        vol.Required(ATTR_ITEM_ID): cv.string,
        vol.Required(ATTR_ZONE): cv.positive_int,
        vol.Required(ATTR_VALUE): vol.Coerce(float),
    }
)

CREATE_VACATION_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.string,
        vol.Optional(ATTR_END_DATE): cv.date,
    }
)


def _get_loaded_entry(hass: HomeAssistant, device_id: str) -> AristonConfigEntry:
    """Resolve a device registry id to the loaded Ariston config entry behind it."""
    device = dr.async_get(hass).async_get(device_id)
    if device is None:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="device_not_found",
            translation_placeholders={"device_id": device_id},
        )
    for entry_id in device.config_entries:
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is not None and entry.domain == DOMAIN:
            if entry.state is not ConfigEntryState.LOADED:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="entry_not_loaded",
                    translation_placeholders={
                        "device": device.name_by_user or device.name or device_id
                    },
                )
            return entry
    raise ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key="device_not_found",
        translation_placeholders={"device_id": device_id},
    )


def _require_galevo(entry: AristonConfigEntry, service: str) -> None:
    """Raise when the device is not a Galevo (boiler / heat pump) system."""
    device = entry.runtime_data.device
    if device.system_type is not SystemType.GALEVO:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="service_not_supported",
            translation_placeholders={
                "service": service,
                "device": device.name or "",
                "system_type": device.system_type.name,
            },
        )


async def _async_set_item_by_id(call: ServiceCall) -> None:
    """Write a raw device or thermostat property."""
    entry = _get_loaded_entry(call.hass, call.data[ATTR_DEVICE_ID])
    _require_galevo(entry, SERVICE_SET_ITEM_BY_ID)
    data = entry.runtime_data
    await data.device.async_set_item_by_id(
        call.data[ATTR_ITEM_ID], call.data[ATTR_VALUE], call.data[ATTR_ZONE]
    )
    await data.coordinator.async_request_refresh()


async def _async_create_vacation(call: ServiceCall) -> None:
    """Create (or, without an end date, clear) a holiday period."""
    entry = _get_loaded_entry(call.hass, call.data[ATTR_DEVICE_ID])
    _require_galevo(entry, SERVICE_CREATE_VACATION)
    data = entry.runtime_data
    end_date: date | None = call.data.get(ATTR_END_DATE)
    await data.device.async_set_holiday(end_date)
    data.coordinator.async_update_listeners()


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the integration services once."""
    if hass.services.has_service(DOMAIN, SERVICE_SET_ITEM_BY_ID):
        return
    hass.services.async_register(
        DOMAIN, SERVICE_SET_ITEM_BY_ID, _async_set_item_by_id, schema=SET_ITEM_BY_ID_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_CREATE_VACATION, _async_create_vacation, schema=CREATE_VACATION_SCHEMA
    )
