"""Base entity and shared entity-description plumbing for Ariston."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from typing import Any

from ariston.const import SystemType, WheType, ZoneAttribute

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity, EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTR_PENDING_COMMAND, CONFIGURATION_URL, COORDINATOR, DOMAIN, MANUFACTURER
from .coordinator import AristonConfigEntry, AristonCoordinator

_LOGGER = logging.getLogger(__name__)

# Commercial names for Velis model numbers, as reported by users of those units.
MODEL_NAMES: dict[tuple[WheType, int], str] = {
    (WheType.NuosSplit, 11): "Primos 205 (ARIHPWH-200)",
}


@dataclass(frozen=True, kw_only=True)
class AristonEntityDescription(EntityDescription):
    """Describe one Ariston entity.

    ``system_types`` / ``whe_types`` / ``device_features`` decide whether the entity
    is created for a given device (see ``AristonBaseDevice.are_device_features_available``).
    ``zone=True`` creates one entity per heating zone.
    ``legacy_name`` is the English name versions < 1.0 used to build the unique_id;
    keep it so existing entity registry entries (and their history) survive upgrades.
    """

    coordinator: str = COORDINATOR
    device_features: list[str] | None = None
    system_types: list[SystemType] | None = None
    whe_types: list[WheType] | None = None
    zone: bool = False
    legacy_name: str | None = None
    extra_attributes: dict[str, Callable[[AristonEntity], Any]] | None = None

    def __post_init__(self) -> None:
        """Default the translation key to the description key."""
        if self.translation_key is None:
            object.__setattr__(self, "translation_key", self.key)


def zone_label(device: Any, zone: int) -> str:
    """Return the user-visible name of a heating zone ("Living room" or "Zone 2")."""
    zones = getattr(device, "zones", None)
    if isinstance(zones, list):
        for zone_info in zones:
            if zone_info.get(ZoneAttribute.NUM) == zone and zone_info.get(ZoneAttribute.NAME):
                return str(zone_info[ZoneAttribute.NAME])
    return f"Zone {zone}"


class AristonEntity(CoordinatorEntity[AristonCoordinator]):
    """Common behaviour for every Ariston entity."""

    _attr_has_entity_name = True
    entity_description: AristonEntityDescription

    def __init__(
        self,
        coordinator: AristonCoordinator,
        description: AristonEntityDescription,
        zone: int = 0,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.device = coordinator.device
        self.entity_description = description
        self.zone = zone
        self._attr_unique_id = self._build_unique_id()
        if description.zone:
            self._attr_translation_placeholders = {"zone": zone_label(self.device, zone)}

    def _build_unique_id(self) -> str:
        """Build a unique_id that is byte-identical to the one used before 1.0."""
        gateway = self.device.gateway
        legacy = self.entity_description.legacy_name
        if legacy is not None:
            # Pre-1.0: f"{gateway}-{name}-{zone}" where zone entities had the zone
            # number appended to their name as well.
            if self.zone:
                return f"{gateway}-{legacy} {self.zone}-{self.zone}"
            return f"{gateway}-{legacy}"
        key = self.entity_description.key
        if self.zone:
            return f"{gateway}-{key}-{self.zone}"
        return f"{gateway}-{key}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device registry information."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.device.serial_number or "")},
            manufacturer=MANUFACTURER,
            name=self.device.name,
            model=self.model,
            serial_number=self.device.serial_number,
            sw_version=self.device.firmware_version,
            configuration_url=CONFIGURATION_URL,
        )

    @property
    def model(self) -> str:
        """Return a human readable model string."""
        system = self.device.system_type.name
        whe = self.device.whe_type
        if whe is WheType.Unknown:
            return system
        model_number = self.device.whe_model_type
        if model_number == 0:
            return f"{system} {whe.name}"
        if (name := MODEL_NAMES.get((whe, model_number))) is not None:
            return f"{system} {whe.name} {name}"
        return f"{system} {whe.name} | Model {model_number}"

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the declared extra attributes plus the pending-command flag."""
        attributes: dict[str, Any] = {}
        for name, getter in (self.entity_description.extra_attributes or {}).items():
            value = getter(self)
            if value is not None:
                attributes[name] = value
        if self.coordinator.has_pending_write(self.entity_id):
            attributes[ATTR_PENDING_COMMAND] = True
        return attributes or None

    async def async_write(self, action: Callable[[], Awaitable[Any]], label: str = "") -> None:
        """Send a command to the cloud through the coordinator.

        The coordinator applies a timeout, turns cloud errors into readable
        HomeAssistantErrors, refreshes every entity with the value the library cached,
        polls again soon and keeps that value until the cloud confirms it.
        """
        await self.coordinator.async_execute_write(
            action, entity_id=self.entity_id, label=label or self.entity_id or ""
        )


def build_entities[D: AristonEntityDescription](
    entry: AristonConfigEntry,
    descriptions: Iterable[D],
    factory: Callable[[AristonCoordinator, D, int], Entity],
) -> list[Entity]:
    """Instantiate the entities a device supports from a list of descriptions."""
    entities: list[Entity] = []
    for description in descriptions:
        coordinator = entry.runtime_data.coordinators.get(description.coordinator)
        if coordinator is None:
            # e.g. the energy coordinator only exists for devices with metering.
            continue
        device = coordinator.device
        if not device.are_device_features_available(
            description.device_features,
            description.system_types,
            description.whe_types,
        ):
            continue
        if description.zone:
            entities.extend(factory(coordinator, description, zone) for zone in device.zone_numbers)
        else:
            entities.append(factory(coordinator, description, 0))
    return entities
