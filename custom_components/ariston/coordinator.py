"""Data update coordinators for the Ariston integration."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import timedelta

from ariston.ariston_api import ConnectionException
from ariston.base_device import AristonBaseDevice

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import COORDINATOR, DOMAIN

_LOGGER = logging.getLogger(__name__)

# Messages the ariston library puts into ConnectionException when the session is no
# longer valid. Anything else is treated as a transient cloud/network problem.
_AUTH_ERROR_MARKERS = ("invalid token", "login failed")
_AUTH_HTTP_STATUSES = (401, 403)


def is_auth_error(error: ConnectionException) -> bool:
    """Return True when the library error means our credentials were rejected."""
    for arg in error.args:
        if isinstance(arg, int) and arg in _AUTH_HTTP_STATUSES:
            return True
        if isinstance(arg, str) and any(m in arg.lower() for m in _AUTH_ERROR_MARKERS):
            return True
    return False


class AristonCoordinator(DataUpdateCoordinator[None]):
    """Poll one aspect (state, energy or bus errors) of an Ariston device.

    The ariston library keeps the fetched data on the device object, so this
    coordinator carries no data of its own; entities read from ``coordinator.device``.
    """

    config_entry: AristonConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: AristonConfigEntry,
        device: AristonBaseDevice,
        kind: str,
        scan_interval_seconds: int,
        update_method: Callable[[], Awaitable[None]],
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}-{device.name}-{kind}",
            update_interval=timedelta(seconds=scan_interval_seconds),
        )
        self.device = device
        self.kind = kind
        self._update_method = update_method

    async def _async_update_data(self) -> None:
        """Fetch data from the Ariston cloud, translating library errors for HA."""
        try:
            await self._update_method()
        except ConnectionException as err:
            if is_auth_error(err):
                raise ConfigEntryAuthFailed(
                    f"Ariston rejected the credentials for {self.device.name}"
                ) from err
            raise UpdateFailed(
                f"Error communicating with the Ariston cloud ({self.kind}): {err}"
            ) from err


@dataclass
class AristonData:
    """Runtime data stored on the config entry."""

    device: AristonBaseDevice
    coordinators: dict[str, AristonCoordinator] = field(default_factory=dict)

    @property
    def coordinator(self) -> AristonCoordinator:
        """Return the main (device state) coordinator."""
        return self.coordinators[COORDINATOR]


type AristonConfigEntry = ConfigEntry[AristonData]
