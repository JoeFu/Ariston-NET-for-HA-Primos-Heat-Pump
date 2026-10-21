"""Data update coordinators for the Ariston integration."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from ariston.ariston_api import ConnectionException
from ariston.base_device import AristonBaseDevice

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import COORDINATOR, DOMAIN

_LOGGER = logging.getLogger(__name__)

# Messages the ariston library puts into ConnectionException when the session is no
# longer valid. Anything else is treated as a transient cloud/network problem.
_AUTH_ERROR_MARKERS = ("invalid token", "login failed")
_AUTH_HTTP_STATUSES = (401, 403)

# The ariston library has no request timeout (aiohttp's default is 5 minutes); these
# keep the UI responsive when the cloud hangs.
READ_TIMEOUT = timedelta(seconds=60)
WRITE_TIMEOUT = timedelta(seconds=30)
# After a write the appliance picks the command up from the cloud with some delay; poll
# again soon instead of waiting for the regular interval, and keep showing what we wrote
# until the cloud confirms it or this much time has passed.
WRITE_RECHECK_DELAYS = (timedelta(seconds=10), timedelta(seconds=40))
WRITE_CONFIRM_TIMEOUT = timedelta(minutes=2)

# Device attributes the library mutates locally after a successful write.
_CACHED_CONTAINERS = ("data", "plant_settings", "consumptions_settings")

_MISSING = object()


def is_auth_error(error: ConnectionException) -> bool:
    """Return True when the library error means our credentials were rejected."""
    for arg in error.args:
        if isinstance(arg, int) and arg in _AUTH_HTTP_STATUSES:
            return True
        if isinstance(arg, str) and any(m in arg.lower() for m in _AUTH_ERROR_MARKERS):
            return True
    return False


# --- cache snapshots ----------------------------------------------------------------
# The library updates the device's cached data as part of each write. Comparing a
# snapshot taken before the write with one taken after tells us exactly which values
# the write promised, without the entities having to describe it.

Path = tuple[Any, ...]


def _snapshot(device: AristonBaseDevice) -> dict[str, Any]:
    return {
        name: deepcopy(getattr(device, name))
        for name in _CACHED_CONTAINERS
        if isinstance(getattr(device, name, None), dict)
    }


def _item_key(item: Any) -> tuple[Any, Any] | None:
    if isinstance(item, dict) and "id" in item:
        return (item.get("id"), item.get("zone"))
    return None


def _diff(before: Any, after: Any, path: Path = ()) -> list[tuple[Path, Any]]:
    """Return (path, value) pairs for every leaf that changed from before to after."""
    if isinstance(before, dict) and isinstance(after, dict):
        changes: list[tuple[Path, Any]] = []
        for key, value in after.items():
            if key in before:
                changes.extend(_diff(before[key], value, (*path, key)))
            else:
                changes.append(((*path, key), deepcopy(value)))
        return changes
    if (
        isinstance(before, list)
        and isinstance(after, list)
        and after
        and all(_item_key(item) is not None for item in after)
    ):
        # Lists of cloud "items" are matched by (id, zone) rather than position.
        index = {_item_key(item): item for item in before if _item_key(item) is not None}
        changes = []
        for item in after:
            key = _item_key(item)
            if key in index:
                changes.extend(_diff(index[key], item, (*path, ("item", key))))
        return changes
    if before == after:
        return []
    return [(path, deepcopy(after))]


def _resolve(container: Any, path: Path, create: bool = False) -> tuple[Any, Any]:
    """Walk ``path`` and return (parent, last_key); parent is _MISSING when absent."""
    node = container
    for step in path[:-1]:
        node = _step(node, step)
        if node is _MISSING:
            return _MISSING, None
    return node, path[-1]


def _step(node: Any, step: Any) -> Any:
    if isinstance(step, tuple) and len(step) == 2 and step[0] == "item":
        if not isinstance(node, list):
            return _MISSING
        return next((item for item in node if _item_key(item) == step[1]), _MISSING)
    if isinstance(node, dict):
        return node.get(step, _MISSING)
    return _MISSING


def _get(container: Any, path: Path) -> Any:
    parent, key = _resolve(container, path)
    if parent is _MISSING:
        return _MISSING
    return _step(parent, key)


def _set(container: Any, path: Path, value: Any) -> None:
    parent, key = _resolve(container, path)
    if isinstance(parent, dict):
        parent[key] = deepcopy(value)


@dataclass
class PendingWrite:
    """What a write promised, until the cloud confirms it or it expires."""

    entity_id: str | None
    label: str
    changes: list[tuple[Path, Any]]
    deadline: datetime
    confirmed: int = 0

    def describe(self) -> str:
        """Human readable summary of the written values."""
        parts = []
        for path, value in self.changes:
            leaf = path[-1]
            parent = path[-2] if len(path) > 1 else None
            name = parent[1][0] if isinstance(parent, tuple) else leaf
            parts.append(f"{name}={value}")
        return ", ".join(parts) or self.label


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
        self._pending: list[PendingWrite] = []
        self._recheck_unsubs: list[CALLBACK_TYPE] = []

    # --- reads -----------------------------------------------------------------

    async def _async_update_data(self) -> None:
        """Fetch data from the Ariston cloud, translating library errors for HA."""
        try:
            async with asyncio.timeout(READ_TIMEOUT.total_seconds()):
                await self._update_method()
        except TimeoutError as err:
            raise UpdateFailed(
                f"The Ariston cloud did not answer within {READ_TIMEOUT.seconds} s ({self.kind})"
            ) from err
        except ConnectionException as err:
            if is_auth_error(err):
                raise ConfigEntryAuthFailed(
                    f"Ariston rejected the credentials for {self.device.name}"
                ) from err
            raise UpdateFailed(
                f"Error communicating with the Ariston cloud ({self.kind}): {err}"
            ) from err
        self._reconcile_pending()

    # --- writes ----------------------------------------------------------------

    async def async_execute_write(
        self,
        action: Callable[[], Awaitable[Any]],
        *,
        entity_id: str | None = None,
        label: str = "",
    ) -> None:
        """Run a write against the cloud with a timeout and clear errors.

        On success the values the library cached are remembered as a pending write:
        every entity is refreshed immediately, the cloud is polled again shortly, and
        the written values keep winning over stale cloud data until confirmed.
        """
        before = _snapshot(self.device)
        try:
            async with asyncio.timeout(WRITE_TIMEOUT.total_seconds()):
                await action()
        except TimeoutError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="write_timeout",
                translation_placeholders={
                    "entity": entity_id or self.device.name or "",
                    "timeout": str(WRITE_TIMEOUT.seconds),
                },
            ) from err
        except ConnectionException as err:
            if is_auth_error(err):
                self.config_entry.async_start_reauth(self.hass)
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="write_failed",
                translation_placeholders={
                    "entity": entity_id or self.device.name or "",
                    "error": str(err) or err.__class__.__name__,
                },
            ) from err

        changes = _diff(before, _snapshot(self.device))
        if changes:
            self._pending.append(
                PendingWrite(
                    entity_id=entity_id,
                    label=label,
                    changes=changes,
                    deadline=dt_util.utcnow() + WRITE_CONFIRM_TIMEOUT,
                )
            )
            self._schedule_rechecks()
        self.async_update_listeners()

    @callback
    def has_pending_write(self, entity_id: str | None) -> bool:
        """Return True while a write made by this entity awaits cloud confirmation."""
        return any(pending.entity_id == entity_id for pending in self._pending)

    @callback
    def _schedule_rechecks(self) -> None:
        """Poll the cloud again soon so the real state shows up before the next interval."""
        self._cancel_rechecks()

        async def _recheck(_now: datetime) -> None:
            await self.async_request_refresh()

        self._recheck_unsubs = [
            async_call_later(self.hass, delay.total_seconds(), _recheck)
            for delay in WRITE_RECHECK_DELAYS
        ]

    @callback
    def _cancel_rechecks(self) -> None:
        for unsub in self._recheck_unsubs:
            unsub()
        self._recheck_unsubs = []

    @callback
    def _reconcile_pending(self) -> None:
        """After a poll: drop confirmed writes, re-apply unconfirmed ones, expire old ones."""
        if not self._pending:
            return
        now = dt_util.utcnow()
        live = {name: getattr(self.device, name, None) for name in _CACHED_CONTAINERS}
        still_pending: list[PendingWrite] = []
        for pending in self._pending:
            remaining = []
            for path, expected in pending.changes:
                if _get(live, path) == expected:
                    pending.confirmed += 1
                else:
                    remaining.append((path, expected))
            pending.changes = remaining
            if not remaining:
                _LOGGER.debug("Write confirmed by the cloud: %s", pending.label)
                continue
            if now >= pending.deadline:
                self._expire(pending)
                continue
            # Not confirmed yet: keep showing what we wrote instead of the stale value.
            for path, expected in remaining:
                _set(live, path, expected)
            still_pending.append(pending)
        self._pending = still_pending

    def _expire(self, pending: PendingWrite) -> None:
        if pending.confirmed:
            # Part of the write was confirmed (e.g. the target temperature) while the
            # cloud reports a different helper value; that is not a failure.
            _LOGGER.debug("Write partly confirmed, dropping the rest: %s", pending.label)
            return
        _LOGGER.warning(
            "%s: the cloud did not confirm %s (%s) within %s; showing the cloud's value",
            self.device.name,
            pending.label,
            pending.describe(),
            WRITE_CONFIRM_TIMEOUT,
        )
        persistent_notification.async_create(
            self.hass,
            (
                f"The command sent to **{self.device.name}** via `{pending.entity_id or pending.label}` "
                f"({pending.describe()}) was not confirmed by the Ariston cloud within "
                f"{WRITE_CONFIRM_TIMEOUT.seconds // 60} minutes. The entity now shows the cloud's value; "
                "check the appliance or try again."
            ),
            title="Ariston command not confirmed",
            notification_id=f"{DOMAIN}_unconfirmed_{self.device.gateway}",
        )

    async def async_shutdown(self) -> None:
        """Cancel scheduled rechecks and shut down."""
        self._cancel_rechecks()
        await super().async_shutdown()


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
