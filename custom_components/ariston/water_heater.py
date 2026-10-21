"""Water heater entities for Ariston devices."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from ariston.const import CustomDeviceFeatures, SystemType, WheType

from homeassistant.components.water_heater import (
    WaterHeaterEntity,
    WaterHeaterEntityDescription,
    WaterHeaterEntityFeature,
)
from homeassistant.const import ATTR_TEMPERATURE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import ATTR_TARGET_TEMP_STEP
from .coordinator import AristonConfigEntry, AristonCoordinator
from .entity import AristonEntity, AristonEntityDescription, build_entities

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class AristonWaterHeaterEntityDescription(WaterHeaterEntityDescription, AristonEntityDescription):
    """Describe an Ariston water heater."""


WATER_HEATER_TYPES: tuple[AristonWaterHeaterEntityDescription, ...] = (
    AristonWaterHeaterEntityDescription(
        key="water_heater",
        extra_attributes={
            ATTR_TARGET_TEMP_STEP: lambda entity: entity.device.water_heater_temperature_step
        },
        device_features=[CustomDeviceFeatures.HAS_DHW],
        system_types=[SystemType.GALEVO, SystemType.BSB],
    ),
    AristonWaterHeaterEntityDescription(
        key="water_heater",
        extra_attributes={
            ATTR_TARGET_TEMP_STEP: lambda entity: entity.device.water_heater_temperature_step
        },
        device_features=[CustomDeviceFeatures.HAS_DHW],
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
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AristonConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Ariston water heater."""
    async_add_entities(build_entities(entry, WATER_HEATER_TYPES, AristonWaterHeater))


class AristonWaterHeater(AristonEntity, WaterHeaterEntity):
    """Domestic hot water of an Ariston system."""

    entity_description: AristonWaterHeaterEntityDescription
    _attr_name = None  # named after the device
    _attr_icon = "mdi:water-boiler"

    def __init__(
        self,
        coordinator: AristonCoordinator,
        description: AristonWaterHeaterEntityDescription,
        zone: int = 0,
    ) -> None:
        """Initialize the water heater."""
        super().__init__(coordinator, description, zone)
        # Keep the pre-1.0 unique_id so entity ids and history survive the upgrade.
        self._attr_unique_id = f"{self.device.gateway}-water_heater"

    @property
    def current_temperature(self) -> float | None:
        """Return the water temperature."""
        return self.device.water_heater_current_temperature

    @property
    def target_temperature(self) -> float | None:
        """Return the target water temperature."""
        return self.device.water_heater_target_temperature

    @property
    def min_temp(self) -> float:
        """Return the minimum target temperature."""
        return self.device.water_heater_minimum_temperature

    @property
    def max_temp(self) -> float:
        """Return the maximum target temperature."""
        return self.device.water_heater_maximum_temperature

    @property
    def precision(self) -> float:
        """Return the temperature precision."""
        return 1 / 10**self.device.water_heater_temperature_decimals

    @property
    def temperature_unit(self) -> str:
        """Return the temperature unit reported by the cloud."""
        return self.device.water_heater_temperature_unit

    @property
    def supported_features(self) -> WaterHeaterEntityFeature:
        """Return the supported features."""
        features = WaterHeaterEntityFeature.TARGET_TEMPERATURE
        if self.device.dhw_mode_changeable:
            features |= WaterHeaterEntityFeature.OPERATION_MODE
        if self.device.system_type is SystemType.VELIS:
            features |= WaterHeaterEntityFeature.ON_OFF
        return features

    @property
    def operation_list(self) -> list[str]:
        """Return the available operation modes."""
        return self.device.water_heater_mode_operation_texts

    @property
    def current_operation(self) -> str | None:
        """Return the current operation mode."""
        return self.device.water_heater_current_mode_text

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set a new target temperature."""
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is None:
            raise ValueError(f"Missing parameter {ATTR_TEMPERATURE}")
        _LOGGER.debug("Setting water temperature to %s for %s", temperature, self.entity_id)
        await self.device.async_set_water_heater_temperature(temperature)
        self.notify_state_written()

    async def async_set_operation_mode(self, operation_mode: str) -> None:
        """Set the operation mode."""
        await self.device.async_set_water_heater_operation_mode(operation_mode)
        self.notify_state_written()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the water heater on."""
        await self.device.async_set_power(True)
        self.notify_state_written()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the water heater off."""
        await self.device.async_set_power(False)
        self.notify_state_written()
