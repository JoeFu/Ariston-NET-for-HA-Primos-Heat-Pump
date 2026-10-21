"""Select entities for Ariston devices."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from ariston.const import DeviceFeatures, PlantMode, SystemType, WheType

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import ENERGY_COORDINATOR, NAME
from .coordinator import AristonConfigEntry, AristonCoordinator
from .entity import AristonEntity, AristonEntityDescription, build_entities


@dataclass(frozen=True, kw_only=True)
class AristonSelectEntityDescription(SelectEntityDescription, AristonEntityDescription):
    """Describe an Ariston select entity."""

    current_option_fn: Callable[[AristonSelect], str | None]
    options_fn: Callable[[AristonSelect], list[str] | None]
    select_option_fn: Callable[[AristonSelect, str], Coroutine[Any, Any, Any]]


async def _async_select_plant_mode(entity: AristonSelect, option: str) -> None:
    """Map the chosen plant-mode text back to the PlantMode the cloud expects."""
    texts = entity.device.plant_mode_opt_texts or []
    values = entity.device.plant_mode_options or []
    index = texts.index(option)
    await entity.device.async_set_plant_mode(PlantMode(values[index]))


SELECT_TYPES: tuple[AristonSelectEntityDescription, ...] = (
    AristonSelectEntityDescription(
        # New: Summer / Winter / Heating only / ... without going through climate presets.
        key="plant_mode",
        icon="mdi:home-thermometer-outline",
        current_option_fn=lambda entity: entity.device.plant_mode_text,
        options_fn=lambda entity: entity.device.plant_mode_opt_texts,
        select_option_fn=_async_select_plant_mode,
        system_types=[SystemType.GALEVO],
    ),
    AristonSelectEntityDescription(
        key="hybrid_mode",
        legacy_name=f"{NAME} hybrid mode",
        icon="mdi:cog",
        entity_category=EntityCategory.CONFIG,
        device_features=[DeviceFeatures.HYBRID_SYS],
        current_option_fn=lambda entity: entity.device.hybrid_mode,
        options_fn=lambda entity: entity.device.hybrid_mode_opt_texts,
        select_option_fn=lambda entity, option: entity.device.async_set_hybrid_mode(option),
        system_types=[SystemType.GALEVO],
    ),
    AristonSelectEntityDescription(
        key="buffer_control_mode",
        legacy_name=f"{NAME} buffer control mode",
        icon="mdi:cup-water",
        entity_category=EntityCategory.CONFIG,
        device_features=[DeviceFeatures.BUFFER_TIME_PROG_AVAILABLE],
        current_option_fn=lambda entity: entity.device.buffer_control_mode,
        options_fn=lambda entity: entity.device.buffer_control_mode_opt_texts,
        select_option_fn=lambda entity, option: entity.device.async_set_buffer_control_mode(option),
        system_types=[SystemType.GALEVO],
    ),
    AristonSelectEntityDescription(
        key="currency",
        legacy_name=f"{NAME} currency",
        icon="mdi:cash-100",
        entity_category=EntityCategory.CONFIG,
        device_features=[DeviceFeatures.HAS_METERING],
        coordinator=ENERGY_COORDINATOR,
        current_option_fn=lambda entity: entity.device.currency,
        options_fn=lambda entity: entity.device.get_currencies(),
        select_option_fn=lambda entity, option: entity.device.async_set_currency(option),
        system_types=[SystemType.GALEVO],
    ),
    AristonSelectEntityDescription(
        key="gas_type",
        legacy_name=f"{NAME} gas type",
        icon="mdi:gas-cylinder",
        entity_category=EntityCategory.CONFIG,
        device_features=[DeviceFeatures.HAS_METERING],
        coordinator=ENERGY_COORDINATOR,
        current_option_fn=lambda entity: entity.device.gas_type,
        options_fn=lambda entity: entity.device.get_gas_types(),
        select_option_fn=lambda entity, option: entity.device.async_set_gas_type(option),
        system_types=[SystemType.GALEVO],
    ),
    AristonSelectEntityDescription(
        key="gas_energy_unit",
        legacy_name=f"{NAME} gas energy unit",
        icon="mdi:cube-scan",
        entity_category=EntityCategory.CONFIG,
        device_features=[DeviceFeatures.HAS_METERING],
        coordinator=ENERGY_COORDINATOR,
        current_option_fn=lambda entity: entity.device.gas_energy_unit,
        options_fn=lambda entity: entity.device.get_gas_energy_units(),
        select_option_fn=lambda entity, option: entity.device.async_set_gas_energy_unit(option),
        system_types=[SystemType.GALEVO],
    ),
    AristonSelectEntityDescription(
        key="operation_mode",
        legacy_name=f"{NAME} operation mode",
        icon="mdi:cog",
        current_option_fn=lambda entity: entity.device.water_heater_current_mode_text,
        options_fn=lambda entity: entity.device.water_heater_mode_operation_texts,
        select_option_fn=lambda entity, option: entity.device.async_set_water_heater_operation_mode(
            option
        ),
        system_types=[SystemType.VELIS],
        whe_types=[WheType.Evo],
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AristonConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Ariston select entities."""
    async_add_entities(build_entities(entry, SELECT_TYPES, AristonSelect))


class AristonSelect(AristonEntity, SelectEntity):
    """An Ariston select entity."""

    entity_description: AristonSelectEntityDescription

    def __init__(
        self,
        coordinator: AristonCoordinator,
        description: AristonSelectEntityDescription,
        zone: int = 0,
    ) -> None:
        """Initialize the select."""
        super().__init__(coordinator, description, zone)

    @property
    def current_option(self) -> str | None:
        """Return the selected option."""
        option = self.entity_description.current_option_fn(self)
        if option is None or option not in self.options:
            return None
        return option

    @property
    def options(self) -> list[str]:
        """Return the available options."""
        return list(self.entity_description.options_fn(self) or [])

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        await self.async_write(lambda: self.entity_description.select_option_fn(self, option))
