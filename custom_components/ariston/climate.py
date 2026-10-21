"""Climate (heating zone) entities for Ariston boilers and heat pumps."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from ariston.const import BsbZoneMode, PlantMode, SystemType, ZoneMode

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityDescription,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import ATTR_ECONOMY_TEMP, ATTR_HEAT_REQUEST, ATTR_ZONE
from .coordinator import AristonConfigEntry, AristonCoordinator
from .entity import AristonEntity, AristonEntityDescription, build_entities, zone_label

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class AristonClimateEntityDescription(ClimateEntityDescription, AristonEntityDescription):
    """Describe an Ariston climate entity."""


CLIMATE_TYPES: tuple[AristonClimateEntityDescription, ...] = (
    AristonClimateEntityDescription(
        key="thermostat",
        zone=True,
        extra_attributes={
            ATTR_HEAT_REQUEST: lambda entity: entity.device.get_zone_heat_request_value(
                entity.zone
            ),
            ATTR_ECONOMY_TEMP: lambda entity: entity.device.get_zone_economy_temp_value(
                entity.zone
            ),
            ATTR_ZONE: lambda entity: entity.zone,
        },
        system_types=[SystemType.GALEVO],
    ),
    AristonClimateEntityDescription(
        key="thermostat",
        zone=True,
        extra_attributes={ATTR_ZONE: lambda entity: entity.zone},
        system_types=[SystemType.BSB],
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AristonConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up one climate entity per heating zone."""
    async_add_entities(build_entities(entry, CLIMATE_TYPES, AristonThermostat))


class AristonThermostat(AristonEntity, ClimateEntity):
    """A heating zone of an Ariston system."""

    entity_description: AristonClimateEntityDescription
    _enable_turn_on_off_backwards_compatibility = False

    def __init__(
        self,
        coordinator: AristonCoordinator,
        description: AristonClimateEntityDescription,
        zone: int,
    ) -> None:
        """Initialize the thermostat."""
        super().__init__(coordinator, description, zone)
        # Keep the pre-1.0 unique_id so entity ids and history survive the upgrade.
        self._attr_unique_id = f"{self.device.gateway}_{zone}"
        # A single-zone system is simply named after the device; multi-zone systems
        # get the zone name the user configured in the Ariston app.
        self._attr_translation_placeholders = {}
        self._attr_name = (
            None if len(self.device.zone_numbers) <= 1 else zone_label(self.device, zone)
        )

    @property
    def icon(self) -> str:
        """Return an icon that reflects whether heating is enabled."""
        if self.device.is_plant_in_heat_mode:
            return "mdi:radiator"
        return "mdi:radiator-off"

    @property
    def temperature_unit(self) -> str:
        """Return the temperature unit reported by the cloud."""
        return self.device.get_measured_temp_unit(self.zone)

    @property
    def precision(self) -> float:
        """Return the precision of the measured temperature."""
        return 1 / 10 ** self.device.get_measured_temp_decimals(self.zone)

    @property
    def min_temp(self) -> float:
        """Return the minimum target temperature."""
        return self.device.get_comfort_temp_min(self.zone)

    @property
    def max_temp(self) -> float:
        """Return the maximum target temperature."""
        return self.device.get_comfort_temp_max(self.zone)

    @property
    def target_temperature_step(self) -> float:
        """Return the target temperature step."""
        return self.device.get_target_temp_step(self.zone)

    @property
    def current_temperature(self) -> float | None:
        """Return the measured room temperature."""
        return self.device.get_measured_temp_value(self.zone)

    @property
    def target_temperature(self) -> float | None:
        """Return the target temperature."""
        return self.device.get_target_temp_value(self.zone)

    @property
    def supported_features(self) -> ClimateEntityFeature:
        """Return the supported features."""
        features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.TURN_OFF
            | ClimateEntityFeature.TURN_ON
        )
        if self.device.plant_mode_supported:
            features |= ClimateEntityFeature.PRESET_MODE
        return features

    @property
    def hvac_mode(self) -> HVACMode:
        """Return the current HVAC mode."""
        if self.device.is_plant_in_heat_mode:
            if self.device.is_zone_in_manual_mode(self.zone):
                return HVACMode.HEAT
            if self.device.is_zone_in_time_program_mode(self.zone):
                return HVACMode.AUTO
        if self.device.is_plant_in_cool_mode:
            if self.device.is_zone_in_manual_mode(self.zone):
                return HVACMode.COOL
            if self.device.is_zone_in_time_program_mode(self.zone):
                return HVACMode.AUTO
        return HVACMode.OFF

    @property
    def hvac_modes(self) -> list[HVACMode]:
        """Return the HVAC modes this zone supports."""
        modes: list[HVACMode] = []
        if self.device.is_zone_mode_options_contains_manual(self.zone):
            modes.append(HVACMode.HEAT)
            if (
                self.device.plant_mode_supported
                and self.device.is_plant_mode_options_contains_cooling
            ):
                modes.append(HVACMode.COOL)
        if self.device.is_zone_mode_options_contains_time_program(self.zone):
            modes.append(HVACMode.AUTO)
        if self.device.is_zone_mode_options_contains_off(self.zone):
            modes.append(HVACMode.OFF)
        return modes

    @property
    def hvac_action(self) -> HVACAction:
        """Return what the appliance is doing right now."""
        active = bool(self.device.is_flame_on_value) or bool(
            getattr(self.device, "is_heating_pump_on_value", False)
        )
        if self.device.is_plant_in_heat_mode:
            return HVACAction.HEATING if active else HVACAction.IDLE
        if self.device.is_plant_in_cool_mode:
            return HVACAction.COOLING if active else HVACAction.IDLE
        return HVACAction.OFF

    @property
    def preset_mode(self) -> str | None:
        """Return the plant mode (Summer / Winter / ...) as the preset."""
        if not self.device.plant_mode_supported:
            return None
        return self.device.plant_mode_text

    @property
    def preset_modes(self) -> list[str] | None:
        """Return the plant modes the appliance offers."""
        if not self.device.plant_mode_supported:
            return None
        return self.device.plant_mode_opt_texts

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set a new HVAC mode, adjusting the plant mode when needed."""
        await self.async_write(lambda: self._async_write_hvac_mode(hvac_mode), "set_hvac_mode")

    async def _async_write_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if self.device.plant_mode_supported:
            await self._async_set_galevo_hvac_mode(hvac_mode)
        elif hvac_mode == HVACMode.OFF:
            await self.device.async_set_zone_mode(BsbZoneMode.OFF, self.zone)
        elif hvac_mode == HVACMode.AUTO:
            await self.device.async_set_zone_mode(BsbZoneMode.TIME_PROGRAM, self.zone)
        elif hvac_mode == HVACMode.HEAT:
            await self.device.async_set_zone_mode(BsbZoneMode.MANUAL, self.zone)

    async def _async_set_galevo_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """HVAC mode handling for systems with a plant mode (Galevo)."""
        plant_modes = self.device.plant_mode_options
        zone_modes = self.device.get_zone_mode_options(self.zone)
        current_plant_mode = self.device.plant_mode
        manual_mode = (
            ZoneMode.MANUAL_NIGHT if ZoneMode.MANUAL_NIGHT in zone_modes else ZoneMode.MANUAL
        )

        if hvac_mode == HVACMode.OFF:
            if self.device.is_plant_mode_options_contains_off:
                await self.device.async_set_plant_mode(PlantMode.OFF)
            else:
                await self.device.async_set_plant_mode(PlantMode.SUMMER)
            return

        if hvac_mode == HVACMode.COOL:
            await self.device.async_set_plant_mode(PlantMode.COOLING)
            await self.device.async_set_zone_mode(manual_mode, self.zone)
            return

        # HEAT and AUTO both need the plant to be heating.
        heating_modes = (
            [PlantMode.WINTER, PlantMode.HEATING_ONLY, PlantMode.COOLING]
            if hvac_mode == HVACMode.AUTO
            else [PlantMode.WINTER, PlantMode.HEATING_ONLY]
        )
        if current_plant_mode in heating_modes:
            pass  # already heating (or cooling in AUTO): only the zone mode changes
        elif current_plant_mode in (PlantMode.SUMMER, PlantMode.COOLING):
            # DHW is active, so use Winter where both CH and DHW run.
            await self.device.async_set_plant_mode(PlantMode.WINTER)
        elif PlantMode.HEATING_ONLY in plant_modes:
            await self.device.async_set_plant_mode(PlantMode.HEATING_ONLY)
        else:
            await self.device.async_set_plant_mode(PlantMode.WINTER)

        if hvac_mode == HVACMode.AUTO:
            await self.device.async_set_zone_mode(ZoneMode.TIME_PROGRAM, self.zone)
        else:
            await self.device.async_set_zone_mode(manual_mode, self.zone)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set the plant mode."""
        _LOGGER.debug("Setting preset mode to %s for %s", preset_mode, self.entity_id)
        await self.async_write(
            lambda: self._async_write_preset_mode(preset_mode), "set_preset_mode"
        )

    async def _async_write_preset_mode(self, preset_mode: str) -> None:
        texts = self.device.plant_mode_opt_texts
        plant_mode = PlantMode(self.device.plant_mode_options[texts.index(preset_mode)])
        zone_modes = self.device.get_zone_mode_options(self.zone)

        # Leaving cooling: make sure the zone is in a heating-capable state first.
        if (
            self.device.is_plant_in_cool_mode
            and plant_mode != PlantMode.COOLING
            and ZoneMode.MANUAL in zone_modes
        ):
            await self.device.async_set_zone_mode(ZoneMode.MANUAL, self.zone)

        await self.device.async_set_plant_mode(plant_mode)

        if plant_mode == PlantMode.OFF and self.device.is_zone_mode_options_contains_off(self.zone):
            await self.device.async_set_zone_mode(BsbZoneMode.OFF, self.zone)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set a new target temperature."""
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is None:
            raise ValueError(f"Missing parameter {ATTR_TEMPERATURE}")
        _LOGGER.debug("Setting temperature to %s for %s", temperature, self.entity_id)
        await self.async_write(
            lambda: self.device.async_set_comfort_temp(temperature, self.zone), "set_temperature"
        )
