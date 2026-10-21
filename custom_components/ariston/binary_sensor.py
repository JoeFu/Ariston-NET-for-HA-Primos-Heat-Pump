"""Binary sensors for Ariston devices."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ariston.const import DeviceFeatures, SystemType, WheType

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import ATTR_ERRORS, ATTR_HOLIDAY, BUS_ERRORS_COORDINATOR, NAME
from .coordinator import AristonConfigEntry, AristonCoordinator
from .entity import AristonEntity, AristonEntityDescription, build_entities


@dataclass(frozen=True, kw_only=True)
class AristonBinarySensorEntityDescription(BinarySensorEntityDescription, AristonEntityDescription):
    """Describe an Ariston binary sensor."""

    is_on_fn: Callable[[AristonBinarySensor], Any]


BINARY_SENSOR_TYPES: tuple[AristonBinarySensorEntityDescription, ...] = (
    AristonBinarySensorEntityDescription(
        key="flame",
        legacy_name=f"{NAME} is flame on",
        icon="mdi:fire",
        device_class=BinarySensorDeviceClass.HEAT,
        is_on_fn=lambda entity: entity.device.is_flame_on_value,
        system_types=[SystemType.GALEVO, SystemType.BSB],
    ),
    AristonBinarySensorEntityDescription(
        key="heating_pump",
        legacy_name=f"{NAME} is heating pump on",
        icon="mdi:heat-pump-outline",
        device_class=BinarySensorDeviceClass.RUNNING,
        is_on_fn=lambda entity: entity.device.is_heating_pump_on_value,
        device_features=[DeviceFeatures.HYBRID_SYS],
        system_types=[SystemType.GALEVO],
    ),
    AristonBinarySensorEntityDescription(
        key="holiday_mode",
        legacy_name=f"{NAME} holiday mode",
        icon="mdi:island",
        extra_attributes={ATTR_HOLIDAY: lambda entity: entity.device.holiday_expires_on},
        is_on_fn=lambda entity: entity.device.holiday_mode_value,
        system_types=[SystemType.GALEVO],
    ),
    AristonBinarySensorEntityDescription(
        # New: per zone "is this zone asking for heat", previously a climate attribute.
        key="zone_heat_request",
        zone=True,
        device_class=BinarySensorDeviceClass.HEAT,
        is_on_fn=lambda entity: entity.device.get_zone_heat_request_value(entity.zone),
        system_types=[SystemType.GALEVO],
    ),
    AristonBinarySensorEntityDescription(
        key="heating",
        legacy_name=f"{NAME} is heating",
        icon="mdi:fire",
        device_class=BinarySensorDeviceClass.HEAT,
        is_on_fn=lambda entity: entity.device.is_heating,
        system_types=[SystemType.VELIS],
        whe_types=[
            WheType.Lux,
            WheType.Evo,
            WheType.Evo2,
            WheType.Lydos,
            WheType.LydosHybrid,
            WheType.Andris2,
            WheType.Lux2,
        ],
    ),
    AristonBinarySensorEntityDescription(
        key="anti_legionella_cycle",
        legacy_name=f"{NAME} anti-legionella cycle",
        icon="mdi:bacteria",
        device_class=BinarySensorDeviceClass.RUNNING,
        is_on_fn=lambda entity: entity.device.is_antileg,
        system_types=[SystemType.VELIS],
        whe_types=[WheType.Evo2, WheType.Lydos, WheType.LydosHybrid, WheType.Andris2],
    ),
    AristonBinarySensorEntityDescription(
        # New: one glance tells whether the appliance reports any fault.
        key="problem",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        coordinator=BUS_ERRORS_COORDINATOR,
        is_on_fn=lambda entity: len(entity.device.bus_errors) > 0,
        extra_attributes={ATTR_ERRORS: lambda entity: entity.device.bus_errors},
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AristonConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Ariston binary sensors."""
    async_add_entities(build_entities(entry, BINARY_SENSOR_TYPES, AristonBinarySensor))


class AristonBinarySensor(AristonEntity, BinarySensorEntity):
    """An Ariston binary sensor."""

    entity_description: AristonBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: AristonCoordinator,
        description: AristonBinarySensorEntityDescription,
        zone: int = 0,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, description, zone)

    @property
    def is_on(self) -> bool | None:
        """Return True if the condition is active."""
        value = self.entity_description.is_on_fn(self)
        if value is None:
            return None
        return bool(value)
