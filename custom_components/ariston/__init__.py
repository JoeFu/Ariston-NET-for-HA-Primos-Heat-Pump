"""The Ariston NET integration."""

from __future__ import annotations

import logging

from ariston import Ariston, DeviceAttribute
from ariston.ariston_api import ConnectionException
from ariston.const import ARISTON_API_URL, ARISTON_USER_AGENT

from homeassistant.const import CONF_DEVICE, CONF_PASSWORD, CONF_SCAN_INTERVAL, CONF_USERNAME
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
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

    # The device state is required: without it nothing works, so let HA retry setup.
    await coordinators[COORDINATOR].async_config_entry_first_refresh()

    # The fault list and energy history are nice to have. The Ariston cloud sometimes
    # answers these endpoints with HTTP 500 for hours; that must not take the water
    # heater offline. Their entities start unavailable and recover on the next poll.
    failed_optional: list[str] = []
    for kind in (BUS_ERRORS_COORDINATOR, ENERGY_COORDINATOR):
        if (coordinator := coordinators.get(kind)) is None:
            continue
        try:
            await coordinator.async_config_entry_first_refresh()
        except ConfigEntryNotReady as err:
            failed_optional.append(kind)
            _LOGGER.warning(
                "%s: could not load %s during setup, continuing without it for now: %s",
                device_name,
                kind,
                err,
            )

    entry.runtime_data = AristonData(device=device, coordinators=coordinators)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    if ENERGY_COORDINATOR in failed_optional:
        _reload_when_energy_recovers(hass, entry, coordinators[ENERGY_COORDINATOR])
    return True


@callback
def _reload_when_energy_recovers(
    hass: HomeAssistant, entry: AristonConfigEntry, coordinator: AristonCoordinator
) -> None:
    """Reload once the energy data arrives, so the energy sensors get created.

    Which energy sensors exist depends on the consumption types the cloud reports, which
    are only known after a successful energy poll.
    """
    remove: CALLBACK_TYPE | None = None

    @callback
    def _stop() -> None:
        nonlocal remove
        if remove is not None:
            remove()
            remove = None

    @callback
    def _check() -> None:
        if coordinator.last_update_success:
            _stop()
            _LOGGER.info("%s: energy data is available now, reloading", entry.title)
            hass.config_entries.async_schedule_reload(entry.entry_id)

    remove = coordinator.async_add_listener(_check)
    entry.async_on_unload(_stop)


async def _async_update_listener(hass: HomeAssistant, entry: AristonConfigEntry) -> None:
    """Reload the entry when its options change (new polling intervals)."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: AristonConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
