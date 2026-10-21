"""The Ariston NET integration."""

from __future__ import annotations

import logging

from ariston import Ariston, DeviceAttribute
from ariston.ariston_api import ConnectionException
from ariston.const import ARISTON_API_URL, ARISTON_USER_AGENT

from homeassistant.const import CONF_DEVICE, CONF_PASSWORD, CONF_SCAN_INTERVAL, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType
from homeassistant.util.unit_system import METRIC_SYSTEM

from .const import (
    API_URL_SETTING,
    API_USER_AGENT,
    BUS_ERRORS_COORDINATOR,
    BUS_ERRORS_SCAN_INTERVAL,
    COORDINATOR,
    DEFAULT_BUS_ERRORS_SCAN_INTERVAL_SECONDS,
    DEFAULT_ENERGY_SCAN_INTERVAL_MINUTES,
    DEFAULT_SCAN_INTERVAL_SECONDS,
    DOMAIN,
    ENERGY_COORDINATOR,
    ENERGY_SCAN_INTERVAL,
    PLATFORMS,
)
from .coordinator import AristonConfigEntry, AristonCoordinator, AristonData, is_auth_error
from .services import async_setup_services

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register integration-wide services."""
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: AristonConfigEntry) -> bool:
    """Set up one Ariston device from a config entry."""
    device_name = entry.data[CONF_DEVICE].get(DeviceAttribute.NAME, entry.title)
    gateway = entry.data[CONF_DEVICE][DeviceAttribute.GW]
    ariston = Ariston()

    try:
        connected = await ariston.async_connect(
            entry.data[CONF_USERNAME],
            entry.data[CONF_PASSWORD],
            entry.data.get(API_URL_SETTING, ARISTON_API_URL),
            entry.data.get(API_USER_AGENT, ARISTON_USER_AGENT),
        )
    except ConnectionException as err:
        if is_auth_error(err):
            raise ConfigEntryAuthFailed("Ariston rejected the credentials") from err
        raise ConfigEntryNotReady(f"Cannot reach the Ariston cloud: {err}") from err
    if not connected:
        raise ConfigEntryAuthFailed(f"Login to Ariston failed for {device_name}")

    try:
        device = await ariston.async_hello(gateway, hass.config.units is METRIC_SYSTEM)
        if device is None:
            raise ConfigEntryNotReady(
                f"Device {device_name} ({gateway}) was not returned by the Ariston cloud"
            )
        await device.async_get_features()
    except ConnectionException as err:
        raise ConfigEntryNotReady(f"Cannot load {device_name}: {err}") from err

    coordinators: dict[str, AristonCoordinator] = {
        COORDINATOR: AristonCoordinator(
            hass,
            entry,
            device,
            COORDINATOR,
            entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_SECONDS),
            device.async_update_state,
        ),
        BUS_ERRORS_COORDINATOR: AristonCoordinator(
            hass,
            entry,
            device,
            BUS_ERRORS_COORDINATOR,
            entry.options.get(BUS_ERRORS_SCAN_INTERVAL, DEFAULT_BUS_ERRORS_SCAN_INTERVAL_SECONDS),
            device.async_get_bus_errors,
        ),
    }
    if device.has_metering:
        coordinators[ENERGY_COORDINATOR] = AristonCoordinator(
            hass,
            entry,
            device,
            ENERGY_COORDINATOR,
            entry.options.get(ENERGY_SCAN_INTERVAL, DEFAULT_ENERGY_SCAN_INTERVAL_MINUTES) * 60,
            device.async_update_energy,
        )

    for coordinator in coordinators.values():
        await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = AristonData(device=device, coordinators=coordinators)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: AristonConfigEntry) -> None:
    """Reload the entry when its options change (new polling intervals)."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: AristonConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
