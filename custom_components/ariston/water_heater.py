"""Water heater entities for Ariston devices."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from ariston.const import (
    CustomDeviceFeatures,
    NuosSplitOperativeMode,
    NuosSplitProperties,
    SeDeviceSettings,
    SlpDeviceSettings,
    SystemType,
    WheType,
)

from homeassistant.components.water_heater import (
    STATE_OFF,
    WaterHeaterEntity,
    WaterHeaterEntityDescription,
    WaterHeaterEntityFeature,
)
from homeassistant.const import ATTR_TEMPERATURE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import ATTR_TARGET_TEMP_STEP, ATTR_TEMPERATURE_LIMITS
from .coordinator import AristonConfigEntry, AristonCoordinator
from .entity import AristonEntity, AristonEntityDescription, build_entities

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class AristonWaterHeaterEntityDescription(WaterHeaterEntityDescription, AristonEntityDescription):
    """Describe an Ariston water heater."""


@dataclass(frozen=True, kw_only=True)
class ModeLimit:
    """Setpoint limits a mode imposes on top of the installer limits (T_SET_MIN / T_SET_MAX).

    ``min_temp`` is a fixed lower bound. ``max_setting`` names the plant setting that holds
    the upper bound (e.g. the heat-pump-only maximum); ``max_temp`` is used when the
    cloud does not report that setting.
    """

    min_temp: float | None = None
    max_setting: str | None = None
    max_temp: float | None = None


# Per model and operation mode, from the Ariston user manuals:
# - Nuos Split / Primos: GREEN runs the heat pump only, so its ceiling is "T MAX HP"
#   (installer parameter P07, 60 °C by default, exposed by the cloud as
#   SlpMaxGreenTemperature). COMFORT and BOOST (called FAST by the cloud) may use the
#   heating element up to "T MAX" (P09, 70 °C by default). i-Memory keeps the comfort
#   temperature at or above "T_MIN_IMEMORY" (P10, 50 °C by default, not exposed by the cloud).
# - Lydos Hybrid: GREEN is capped by SeMaxGreenSetpointTemperature when the cloud reports it.
MODE_LIMITS: dict[WheType, dict[str, ModeLimit]] = {
    WheType.NuosSplit: {
        "green": ModeLimit(max_setting=SlpDeviceSettings.SLP_MAX_GREEN_TEMPERATURE, max_temp=60),
        "imemory": ModeLimit(min_temp=50),
    },
    WheType.LydosHybrid: {
        "green": ModeLimit(max_setting=SeDeviceSettings.SE_MAX_GREEN_SETPOINT_TEMPERATURE),
    },
}

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


def _to_state(mode_text: str | None) -> str | None:
    """Return the Home Assistant state for a cloud mode text.

    Velis modes arrive as enum names (GREEN, COMFORT, ...); Home Assistant states are
    lowercase and only lowercase keys can be translated, so those become green, comfort, ...
    Free-text modes from boilers ("Time based") are passed through unchanged.
    """
    if mode_text is None:
        return None
    if mode_text.replace("_", "").isalnum() and mode_text.isupper():
        return mode_text.lower()
    return mode_text


def _as_float(value: Any) -> float | None:
    """Return the value as a float, or None when the cloud did not provide it."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class AristonWaterHeater(AristonEntity, WaterHeaterEntity):
    """Domestic hot water of an Ariston system."""

    entity_description: AristonWaterHeaterEntityDescription
    _attr_name = None  # named after the device
    _attr_icon = "mdi:water-boiler"
    _attr_translation_key = "water_heater"

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
        self._mode_limits = MODE_LIMITS.get(self.device.whe_type, {})

    # --- power -------------------------------------------------------------------

    @property
    def _has_power_switch(self) -> bool:
        """Velis water heaters can be switched off; boilers only change DHW mode."""
        return self.device.system_type is SystemType.VELIS

    @property
    def _is_powered_off(self) -> bool:
        return self._has_power_switch and self.device.water_heater_power_value is False

    # --- temperatures --------------------------------------------------------------

    def limits_for_mode(self, mode: str | None) -> tuple[float | None, float | None]:
        """Return (min, max) setpoint for a mode: installer limits narrowed by the mode."""
        low = _as_float(self.device.water_heater_minimum_temperature)
        high = _as_float(self.device.water_heater_maximum_temperature)
        limit = self._mode_limits.get((_to_state(mode) or "").lower())
        if limit is None:
            return low, high
        if limit.min_temp is not None:
            low = limit.min_temp if low is None else max(low, limit.min_temp)
        mode_max = None
        if limit.max_setting is not None:
            mode_max = _as_float(getattr(self.device, "plant_settings", {}).get(limit.max_setting))
        if mode_max is None:
            mode_max = limit.max_temp
        if mode_max is not None:
            high = mode_max if high is None else min(high, mode_max)
        return low, high

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
        """Return the minimum target temperature for the current mode."""
        low, _ = self.limits_for_mode(self.device.water_heater_current_mode_text)
        return low if low is not None else super().min_temp

    @property
    def max_temp(self) -> float:
        """Return the maximum target temperature for the current mode."""
        _, high = self.limits_for_mode(self.device.water_heater_current_mode_text)
        return high if high is not None else super().max_temp

    @property
    def precision(self) -> float:
        """Return the temperature precision."""
        return 1 / 10**self.device.water_heater_temperature_decimals

    @property
    def temperature_unit(self) -> str:
        """Return the temperature unit reported by the cloud."""
        return self.device.water_heater_temperature_unit

    # --- modes ---------------------------------------------------------------------

    @property
    def supported_features(self) -> WaterHeaterEntityFeature:
        """Return the supported features."""
        features = WaterHeaterEntityFeature.TARGET_TEMPERATURE
        if self.device.dhw_mode_changeable:
            features |= WaterHeaterEntityFeature.OPERATION_MODE
        if self._has_power_switch:
            features |= WaterHeaterEntityFeature.ON_OFF
        return features

    @property
    def operation_list(self) -> list[str]:
        """Return the available operation modes, with "off" first where supported."""
        modes = [_to_state(text) for text in self.device.water_heater_mode_operation_texts or []]
        if self._has_power_switch:
            modes.insert(0, STATE_OFF)
        return modes

    @property
    def current_operation(self) -> str | None:
        """Return the current operation mode, or "off" when the heater is switched off."""
        if self._is_powered_off:
            return STATE_OFF
        return _to_state(self.device.water_heater_current_mode_text)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Add the per-mode setpoint limits so dashboards and automations can use them."""
        attributes = dict(super().extra_state_attributes or {})
        if self._mode_limits:
            attributes[ATTR_TEMPERATURE_LIMITS] = {
                _to_state(mode): list(self.limits_for_mode(mode))
                for mode in self.device.water_heater_mode_operation_texts or []
            }
        return attributes or None

    # --- commands ------------------------------------------------------------------

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set a new target temperature, clamped to the current mode's limits."""
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is None:
            raise ValueError(f"Missing parameter {ATTR_TEMPERATURE}")
        low, high = self.limits_for_mode(self.device.water_heater_current_mode_text)
        clamped = temperature
        if low is not None:
            clamped = max(clamped, low)
        if high is not None:
            clamped = min(clamped, high)
        if clamped != temperature:
            _LOGGER.warning(
                "%s: %s °C is outside the %s-%s °C range of mode %s, using %s °C",
                self.entity_id,
                temperature,
                low,
                high,
                self.device.water_heater_current_mode_text,
                clamped,
            )
        _LOGGER.debug("Setting water temperature to %s for %s", clamped, self.entity_id)
        await self.async_write(lambda: self._async_write_temperature(clamped), "set_temperature")

    async def _async_write_temperature(self, temperature: float) -> None:
        await self.device.async_set_water_heater_temperature(temperature)
        self._apply_temperature_locally(temperature)

    def _apply_temperature_locally(self, temperature: float) -> None:
        """Mirror a successful temperature write into the cached data.

        ariston 0.19.9 stores the new Nuos Split target under ``procReqTemp`` while the
        target is read from ``comfortTemp``; without this the dial would jump back to the
        old target until the next poll.
        """
        if self.device.whe_type is WheType.NuosSplit:
            self.device.data[NuosSplitProperties.COMFORT_TEMP] = temperature

    async def async_set_operation_mode(self, operation_mode: str) -> None:
        """Set the operation mode; "off" switches the heater off, any other mode switches it on."""
        if operation_mode == STATE_OFF:
            await self.async_turn_off()
            return
        # Map the state ("green") back to the cloud's mode text ("GREEN").
        mode_text = next(
            (
                text
                for text in self.device.water_heater_mode_operation_texts or []
                if text.lower() == operation_mode.lower()
            ),
            operation_mode,
        )
        await self.async_write(lambda: self._async_write_mode(mode_text), "set_operation_mode")

    async def _async_write_mode(self, mode_text: str) -> None:
        # Bring the target into the new mode's range before the appliance applies it.
        low, high = self.limits_for_mode(mode_text)
        target = _as_float(self.target_temperature)
        if target is not None:
            adjusted = target
            if low is not None:
                adjusted = max(adjusted, low)
            if high is not None:
                adjusted = min(adjusted, high)
            if adjusted != target:
                _LOGGER.info(
                    "%s: adjusting target from %s to %s °C for mode %s",
                    self.entity_id,
                    target,
                    adjusted,
                    mode_text,
                )
                await self._async_write_temperature(adjusted)

        if self._is_powered_off:
            await self.device.async_set_power(True)
        await self.device.async_set_water_heater_operation_mode(mode_text)
        self._apply_mode_locally(mode_text)

    def _apply_mode_locally(self, operation_mode: str) -> None:
        """Mirror a successful mode write into the cached data.

        ariston 0.19.9 stores the new Nuos Split mode under the plant-mode key instead of
        ``opMode``, so without this the entity would show the old mode until the next poll.
        """
        if (
            self.device.whe_type is WheType.NuosSplit
            and self.device.water_heater_current_mode_text != operation_mode
            and operation_mode in NuosSplitOperativeMode.__members__
        ):
            self.device.data[NuosSplitProperties.OP_MODE] = NuosSplitOperativeMode[
                operation_mode
            ].value

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the water heater on."""
        await self.async_write(lambda: self.device.async_set_power(True), "turn_on")

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the water heater off."""
        await self.async_write(lambda: self.device.async_set_power(False), "turn_off")
