"""Number entities for Ariston devices."""

from __future__ import annotations

import sys
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from ariston.const import (
    DeviceFeatures,
    SystemType,
    WheType,
)

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
)
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import ENERGY_COORDINATOR, NAME
from .coordinator import AristonConfigEntry, AristonCoordinator
from .entity import AristonEntity, AristonEntityDescription, build_entities


@dataclass(frozen=True, kw_only=True)
class AristonNumberEntityDescription(NumberEntityDescription, AristonEntityDescription):
    """Describe an Ariston number entity."""

    value_fn: Callable[[AristonNumber], Any]
    set_fn: Callable[[AristonNumber, float], Coroutine[Any, Any, Any]]
    min_fn: Callable[[AristonNumber], float | None] | None = None
    max_fn: Callable[[AristonNumber], float | None] | None = None
    step_fn: Callable[[AristonNumber], float | None] | None = None
    unit_fn: Callable[[AristonNumber], str | None] | None = None


NUMBER_TYPES: tuple[AristonNumberEntityDescription, ...] = (
    # --- Energy cost settings (Galevo with metering) -----------------------------
    AristonNumberEntityDescription(
        key="electricity_cost",
        legacy_name=f"{NAME} elec cost",
        icon="mdi:currency-sign",
        entity_category=EntityCategory.CONFIG,
        native_min_value=0,
        native_max_value=sys.maxsize,
        native_step=0.01,
        device_features=[DeviceFeatures.HAS_METERING],
        coordinator=ENERGY_COORDINATOR,
        value_fn=lambda entity: entity.device.elect_cost,
        set_fn=lambda entity, value: entity.device.async_set_elect_cost(value),
        system_types=[SystemType.GALEVO],
    ),
    AristonNumberEntityDescription(
        key="gas_cost",
        legacy_name=f"{NAME} gas cost",
        icon="mdi:currency-sign",
        entity_category=EntityCategory.CONFIG,
        native_min_value=0,
        native_max_value=sys.maxsize,
        native_step=0.01,
        device_features=[DeviceFeatures.HAS_METERING],
        coordinator=ENERGY_COORDINATOR,
        value_fn=lambda entity: entity.device.gas_cost,
        set_fn=lambda entity, value: entity.device.async_set_gas_cost(value),
        system_types=[SystemType.GALEVO],
    ),
    # --- Zone flow settings (Galevo) ---------------------------------------------
    AristonNumberEntityDescription(
        key="heating_flow_temperature",
        legacy_name=f"{NAME} heating flow temperature",
        icon="mdi:thermometer",
        device_class=NumberDeviceClass.TEMPERATURE,
        entity_category=EntityCategory.CONFIG,
        zone=True,
        min_fn=lambda entity: entity.device.get_heating_flow_temp_min(entity.zone),
        max_fn=lambda entity: entity.device.get_heating_flow_temp_max(entity.zone),
        step_fn=lambda entity: entity.device.get_heating_flow_temp_step(entity.zone),
        unit_fn=lambda entity: entity.device.get_heating_flow_temp_unit(entity.zone),
        value_fn=lambda entity: entity.device.get_heating_flow_temp_value(entity.zone),
        set_fn=lambda entity, value: entity.device.async_set_heating_flow_temp(value, entity.zone),
        system_types=[SystemType.GALEVO],
    ),
    AristonNumberEntityDescription(
        key="heating_flow_offset",
        legacy_name=f"{NAME} heating flow offset",
        icon="mdi:progress-wrench",
        entity_category=EntityCategory.CONFIG,
        zone=True,
        min_fn=lambda entity: entity.device.get_heating_flow_offset_min(entity.zone),
        max_fn=lambda entity: entity.device.get_heating_flow_offset_max(entity.zone),
        step_fn=lambda entity: entity.device.get_heating_flow_offset_step(entity.zone),
        unit_fn=lambda entity: entity.device.get_heating_flow_offset_unit(entity.zone),
        value_fn=lambda entity: entity.device.get_heating_flow_offset_value(entity.zone),
        set_fn=lambda entity, value: entity.device.async_set_heating_flow_offset(
            value, entity.zone
        ),
        system_types=[SystemType.GALEVO],
    ),
    # --- Water heater limits -----------------------------------------------------
    AristonNumberEntityDescription(
        key="max_setpoint_temperature",
        legacy_name=f"{NAME} max setpoint temperature",
        icon="mdi:thermometer-high",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_category=EntityCategory.CONFIG,
        native_step=1,
        min_fn=lambda entity: entity.device.water_heater_maximum_setpoint_temperature_minimum,
        max_fn=lambda entity: entity.device.water_heater_maximum_setpoint_temperature_maximum,
        value_fn=lambda entity: entity.device.water_heater_maximum_setpoint_temperature,
        set_fn=lambda entity, value: entity.device.async_set_max_setpoint_temp(value),
        system_types=[SystemType.VELIS],
        whe_types=[
            WheType.Andris2,
            WheType.Evo2,
            WheType.Lux,
            WheType.Lux2,
            WheType.Lydos,
            WheType.LydosHybrid,
            WheType.NuosSplit,
        ],
    ),
    AristonNumberEntityDescription(
        key="min_setpoint_temperature",
        legacy_name=f"{NAME} min setpoint temperature",
        icon="mdi:thermometer-low",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_category=EntityCategory.CONFIG,
        native_step=1,
        min_fn=lambda entity: entity.device.water_heater_minimum_setpoint_temperature_minimum,
        max_fn=lambda entity: entity.device.water_heater_minimum_setpoint_temperature_maximum,
        value_fn=lambda entity: entity.device.water_heater_minimum_setpoint_temperature,
        set_fn=lambda entity, value: entity.device.async_set_min_setpoint_temp(value),
        system_types=[SystemType.VELIS],
        whe_types=[WheType.NuosSplit],
    ),
    AristonNumberEntityDescription(
        key="reduced_temperature",
        legacy_name=f"{NAME} reduced temperature",
        icon="mdi:thermometer-chevron-down",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_category=EntityCategory.CONFIG,
        native_step=1,
        min_fn=lambda entity: entity.device.water_heater_minimum_temperature,
        max_fn=lambda entity: entity.device.water_heater_maximum_temperature,
        value_fn=lambda entity: entity.device.water_heater_reduced_temperature,
        set_fn=lambda entity, value: entity.device.async_set_water_heater_reduced_temperature(
            value
        ),
        system_types=[SystemType.VELIS],
        whe_types=[WheType.NuosSplit],
    ),
    AristonNumberEntityDescription(
        key="requested_showers",
        legacy_name=f"{NAME} requested number of showers",
        icon="mdi:shower-head",
        native_min_value=0,
        native_step=1,
        max_fn=lambda entity: entity.device.max_req_shower,
        value_fn=lambda entity: entity.device.req_shower,
        set_fn=lambda entity, value: entity.device.async_set_water_heater_number_of_showers(
            int(value)
        ),
        system_types=[SystemType.VELIS],
        whe_types=[WheType.Evo],
    ),
    AristonNumberEntityDescription(
        key="anti_cooling_temperature",
        legacy_name=f"{NAME} anti cooling temperature",
        icon="mdi:thermometer-alert",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_category=EntityCategory.CONFIG,
        native_step=1,
        min_fn=lambda entity: entity.device.anti_cooling_temperature_minimum,
        max_fn=lambda entity: entity.device.anti_cooling_temperature_maximum,
        value_fn=lambda entity: entity.device.anti_cooling_temperature_value,
        set_fn=lambda entity, value: entity.device.async_set_cooling_temperature_value(int(value)),
        system_types=[SystemType.VELIS],
        whe_types=[WheType.LydosHybrid],
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AristonConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Ariston number entities."""
    async_add_entities(build_entities(entry, NUMBER_TYPES, AristonNumber))


def _coerce(value: Any) -> float | None:
    """Turn whatever the cloud returned into a float (or None)."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class AristonNumber(AristonEntity, NumberEntity):
    """An Ariston number entity."""

    entity_description: AristonNumberEntityDescription

    def __init__(
        self,
        coordinator: AristonCoordinator,
        description: AristonNumberEntityDescription,
        zone: int = 0,
    ) -> None:
        """Initialize the number."""
        super().__init__(coordinator, description, zone)

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        return _coerce(self.entity_description.value_fn(self))

    @property
    def native_min_value(self) -> float:
        """Return the minimum, from the cloud when available."""
        if self.entity_description.min_fn is not None:
            value = _coerce(self.entity_description.min_fn(self))
            if value is not None:
                return value
        return super().native_min_value

    @property
    def native_max_value(self) -> float:
        """Return the maximum, from the cloud when available."""
        if self.entity_description.max_fn is not None:
            value = _coerce(self.entity_description.max_fn(self))
            if value is not None:
                return value
        return super().native_max_value

    @property
    def native_step(self) -> float:
        """Return the step, from the cloud when available."""
        if self.entity_description.step_fn is not None:
            value = _coerce(self.entity_description.step_fn(self))
            if value:
                return value
        return super().native_step

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the unit, from the cloud when available."""
        if self.entity_description.unit_fn is not None:
            unit = self.entity_description.unit_fn(self)
            if unit:
                return unit
        return super().native_unit_of_measurement

    async def async_set_native_value(self, value: float) -> None:
        """Write a new value."""
        await self.entity_description.set_fn(self, value)
        self.notify_state_written()
