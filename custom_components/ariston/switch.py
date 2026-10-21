"""Switches for Ariston devices."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from ariston.const import (
    DeviceFeatures,
    DeviceProperties,
    SystemType,
    WheType,
)

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import NAME
from .coordinator import AristonConfigEntry, AristonCoordinator
from .entity import AristonEntity, AristonEntityDescription, build_entities
from .plant_settings import NIGHT_MODE, PERMANENT_BOOST, async_set_plant_setting, get_plant_setting


@dataclass(frozen=True, kw_only=True)
class AristonSwitchEntityDescription(SwitchEntityDescription, AristonEntityDescription):
    """Describe an Ariston switch."""

    is_on_fn: Callable[[AristonSwitch], Any]
    set_fn: Callable[[AristonSwitch, bool], Coroutine[Any, Any, Any]]


SWITCH_TYPES: tuple[AristonSwitchEntityDescription, ...] = (
    # --- Boilers / heat pumps ----------------------------------------------------
    AristonSwitchEntityDescription(
        key="automatic_thermoregulation",
        legacy_name=f"{NAME} automatic thermoregulation",
        icon="mdi:radiator",
        device_features=[DeviceFeatures.AUTO_THERMO_REG],
        is_on_fn=lambda entity: entity.device.automatic_thermoregulation,
        set_fn=lambda entity, value: entity.device.async_set_automatic_thermoregulation(value),
        system_types=[SystemType.GALEVO],
    ),
    AristonSwitchEntityDescription(
        key="quiet_mode",
        legacy_name=f"{NAME} is quiet",
        icon="mdi:volume-off",
        entity_category=EntityCategory.CONFIG,
        device_features=[DeviceProperties.IS_QUIET],
        is_on_fn=lambda entity: entity.device.is_quiet_value,
        set_fn=lambda entity, value: entity.device.async_set_is_quiet(value),
        system_types=[SystemType.GALEVO],
    ),
    # --- Water heaters -----------------------------------------------------------
    AristonSwitchEntityDescription(
        key="power",
        legacy_name=f"{NAME} power",
        icon="mdi:power",
        is_on_fn=lambda entity: entity.device.water_heater_power_value,
        set_fn=lambda entity, value: entity.device.async_set_power(value),
        system_types=[SystemType.VELIS],
    ),
    AristonSwitchEntityDescription(
        key="eco_mode",
        legacy_name=f"{NAME} eco mode",
        icon="mdi:leaf",
        is_on_fn=lambda entity: entity.device.water_heater_eco_value,
        set_fn=lambda entity, value: entity.device.async_set_eco_mode(value),
        system_types=[SystemType.VELIS],
        whe_types=[
            WheType.Lux,
            WheType.Evo,
            WheType.Evo2,
            WheType.Lydos,
            WheType.Andris2,
            WheType.Lux2,
        ],
    ),
    AristonSwitchEntityDescription(
        key="power_option",
        legacy_name=f"{NAME} power option",
        icon="mdi:flash",
        entity_category=EntityCategory.CONFIG,
        is_on_fn=lambda entity: entity.device.water_heater_power_option_value,
        set_fn=lambda entity, value: entity.device.async_set_water_heater_power_option(value),
        system_types=[SystemType.VELIS],
        whe_types=[WheType.Lux2],
    ),
    AristonSwitchEntityDescription(
        key="anti_legionella",
        legacy_name=f"{NAME} anti legionella",
        icon="mdi:bacteria-outline",
        entity_category=EntityCategory.CONFIG,
        is_on_fn=lambda entity: entity.device.water_anti_leg_value,
        set_fn=lambda entity, value: entity.device.async_set_antilegionella(value),
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
    AristonSwitchEntityDescription(
        key="preheating",
        legacy_name=f"{NAME} preheating",
        icon="mdi:heat-wave",
        entity_category=EntityCategory.CONFIG,
        is_on_fn=lambda entity: entity.device.water_heater_preheating_on_off,
        set_fn=lambda entity, value: entity.device.async_set_preheating(value),
        system_types=[SystemType.VELIS],
        whe_types=[WheType.NuosSplit],
    ),
    AristonSwitchEntityDescription(
        key="boost",
        legacy_name=f"{NAME} boost",
        icon="mdi:rocket-launch",
        is_on_fn=lambda entity: entity.device.water_heater_boost,
        set_fn=lambda entity, value: entity.device.async_set_water_heater_boost(value),
        system_types=[SystemType.VELIS],
        whe_types=[WheType.NuosSplit],
    ),
    AristonSwitchEntityDescription(
        key="permanent_boost",
        legacy_name=f"{NAME} permanent boost",
        icon="mdi:rocket-launch",
        entity_category=EntityCategory.CONFIG,
        is_on_fn=lambda entity: get_plant_setting(entity.device, PERMANENT_BOOST),
        set_fn=lambda entity, value: async_set_plant_setting(entity.device, PERMANENT_BOOST, value),
        system_types=[SystemType.VELIS],
        whe_types=[WheType.LydosHybrid, WheType.NuosSplit],
    ),
    AristonSwitchEntityDescription(
        key="anti_cooling",
        legacy_name=f"{NAME} anti cooling",
        icon="mdi:snowflake-thermometer",
        entity_category=EntityCategory.CONFIG,
        is_on_fn=lambda entity: entity.device.anti_cooling_value,
        set_fn=lambda entity, value: entity.device.async_set_anti_cooling_value(value),
        system_types=[SystemType.VELIS],
        whe_types=[WheType.LydosHybrid],
    ),
    AristonSwitchEntityDescription(
        key="night_mode",
        legacy_name=f"{NAME} night mode",
        icon="mdi:weather-night",
        entity_category=EntityCategory.CONFIG,
        is_on_fn=lambda entity: get_plant_setting(entity.device, NIGHT_MODE),
        set_fn=lambda entity, value: async_set_plant_setting(entity.device, NIGHT_MODE, value),
        system_types=[SystemType.VELIS],
        whe_types=[WheType.LydosHybrid, WheType.NuosSplit],
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AristonConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Ariston switches."""
    async_add_entities(build_entities(entry, SWITCH_TYPES, AristonSwitch))


class AristonSwitch(AristonEntity, SwitchEntity):
    """An Ariston switch."""

    entity_description: AristonSwitchEntityDescription

    def __init__(
        self,
        coordinator: AristonCoordinator,
        description: AristonSwitchEntityDescription,
        zone: int = 0,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, description, zone)

    @property
    def is_on(self) -> bool | None:
        """Return True if the switch is on."""
        value = self.entity_description.is_on_fn(self)
        if value is None:
            return None
        return bool(value)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        await self.async_write(lambda: self.entity_description.set_fn(self, True))

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self.async_write(lambda: self.entity_description.set_fn(self, False))
