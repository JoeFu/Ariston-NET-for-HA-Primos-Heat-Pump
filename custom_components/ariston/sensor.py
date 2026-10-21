"""Sensors for Ariston devices."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ariston.const import (
    ConsumptionType,
    CustomDeviceFeatures,
    DeviceAttribute,
    DeviceFeatures,
    DeviceProperties,
    SystemType,
    WheType,
)

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfEnergy, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import ATTR_ERRORS, BUS_ERRORS_COORDINATOR, ENERGY_COORDINATOR, NAME
from .coordinator import AristonConfigEntry, AristonCoordinator
from .entity import AristonEntity, AristonEntityDescription, build_entities

ALL_VELIS_WHE_TYPES = [
    WheType.Andris2,
    WheType.Evo,
    WheType.Evo2,
    WheType.Lux,
    WheType.Lux2,
    WheType.Lydos,
    WheType.LydosHybrid,
    WheType.NuosSplit,
]


@dataclass(frozen=True, kw_only=True)
class AristonSensorEntityDescription(SensorEntityDescription, AristonEntityDescription):
    """Describe an Ariston sensor."""

    value_fn: Callable[[AristonSensor], Any]
    unit_fn: Callable[[AristonSensor], str | None] | None = None
    last_reset_fn: Callable[[AristonSensor], datetime | None] | None = None


def _energy_total(
    key: str,
    legacy_name: str,
    consumption_type: ConsumptionType,
    value_fn: Callable[[AristonSensor], Any],
    *,
    system_types: list[SystemType] | None = None,
) -> AristonSensorEntityDescription:
    """Describe one running energy total reported by the cloud."""
    return AristonSensorEntityDescription(
        key=key,
        legacy_name=legacy_name,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        coordinator=ENERGY_COORDINATOR,
        device_features=[DeviceFeatures.HAS_METERING, consumption_type.name],
        system_types=system_types,
        value_fn=value_fn,
        last_reset_fn=lambda entity: entity.device.consumption_sequence_last_changed_utc,
    )


def _energy_last_month(
    key: str,
    legacy_name: str,
    value_fn: Callable[[AristonSensor], Any],
    *,
    extra_features: list[str] | None = None,
) -> AristonSensorEntityDescription:
    """Describe a 'last month' energy figure (Galevo only)."""
    return AristonSensorEntityDescription(
        key=key,
        legacy_name=legacy_name,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        coordinator=ENERGY_COORDINATOR,
        device_features=[DeviceFeatures.HAS_METERING, *(extra_features or [])],
        system_types=[SystemType.GALEVO],
        value_fn=value_fn,
    )


SENSOR_TYPES: tuple[AristonSensorEntityDescription, ...] = (
    # --- Boilers / heat pumps (Galevo, BSB) -------------------------------------
    AristonSensorEntityDescription(
        key="heating_circuit_pressure",
        legacy_name=f"{NAME} heating circuit pressure",
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda entity: entity.device.heating_circuit_pressure_value,
        unit_fn=lambda entity: entity.device.heating_circuit_pressure_unit,
        system_types=[SystemType.GALEVO],
    ),
    AristonSensorEntityDescription(
        key="ch_flow_setpoint_temperature",
        legacy_name=f"{NAME} CH flow setpoint temp",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda entity: entity.device.ch_flow_setpoint_temp_value,
        unit_fn=lambda entity: entity.device.ch_flow_setpoint_temp_unit,
        system_types=[SystemType.GALEVO],
    ),
    AristonSensorEntityDescription(
        key="ch_flow_temperature",
        legacy_name=f"{NAME} CH flow temp",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda entity: entity.device.ch_flow_temp_value,
        unit_fn=lambda entity: entity.device.ch_flow_temp_unit,
        device_features=[DeviceProperties.CH_FLOW_TEMP],
        system_types=[SystemType.GALEVO],
    ),
    AristonSensorEntityDescription(
        key="ch_return_temperature",
        legacy_name=f"{NAME} CH return temp",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda entity: entity.device.ch_return_temp_value,
        unit_fn=lambda entity: entity.device.ch_return_temp_unit,
        system_types=[SystemType.GALEVO],
    ),
    AristonSensorEntityDescription(
        key="outside_temperature",
        legacy_name=f"{NAME} Outside temp",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda entity: entity.device.outside_temp_value,
        unit_fn=lambda entity: entity.device.outside_temp_unit,
        device_features=[CustomDeviceFeatures.HAS_OUTSIDE_TEMP],
        system_types=[SystemType.GALEVO, SystemType.BSB],
    ),
    AristonSensorEntityDescription(
        # New: the tank / DHW temperature as a plain sensor so it can be graphed.
        key="hot_water_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda entity: entity.device.water_heater_current_temperature,
        unit_fn=lambda entity: entity.device.water_heater_temperature_unit,
        device_features=[CustomDeviceFeatures.HAS_DHW],
        system_types=[SystemType.GALEVO, SystemType.BSB],
    ),
    AristonSensorEntityDescription(
        # New: per zone economy (reduced) setpoint, previously only a climate attribute.
        key="zone_economy_temperature",
        zone=True,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda entity: entity.device.get_zone_economy_temp_value(entity.zone),
        unit_fn=lambda entity: entity.device.get_measured_temp_unit(entity.zone),
        system_types=[SystemType.GALEVO],
    ),
    AristonSensorEntityDescription(
        key="signal_strength",
        legacy_name=f"{NAME} signal strength",
        icon="mdi:wifi",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda entity: entity.device.signal_strength_value,
        unit_fn=lambda entity: entity.device.signal_strength_unit,
        system_types=[SystemType.GALEVO],
    ),
    # --- Water heaters (Velis family) ------------------------------------------
    AristonSensorEntityDescription(
        # Previously Velis Evo only; every Velis model reports a tank temperature.
        key="current_temperature",
        legacy_name=f"{NAME} current temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda entity: entity.device.water_heater_current_temperature,
        system_types=[SystemType.VELIS],
        whe_types=ALL_VELIS_WHE_TYPES,
    ),
    AristonSensorEntityDescription(
        key="requested_temperature_progress",
        legacy_name=f"{NAME} proc req temp",
        icon="mdi:thermometer-auto",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda entity: entity.device.proc_req_temp_value,
        system_types=[SystemType.VELIS],
        whe_types=[
            WheType.NuosSplit,
            WheType.Evo2,
            WheType.LydosHybrid,
            WheType.Lydos,
            WheType.Andris2,
            WheType.Lux,
            WheType.Lux2,
        ],
    ),
    AristonSensorEntityDescription(
        key="average_showers",
        legacy_name=f"{NAME} average showers",
        icon="mdi:shower-head",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda entity: entity.device.av_shw_value,
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
    AristonSensorEntityDescription(
        key="remaining_time",
        legacy_name=f"{NAME} remaining time",
        icon="mdi:timer-outline",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        value_fn=lambda entity: entity.device.rm_tm_in_minutes,
        system_types=[SystemType.VELIS],
        whe_types=[WheType.Lux, WheType.Evo, WheType.Evo2, WheType.Lux2, WheType.Lydos],
    ),
    AristonSensorEntityDescription(
        key="heating_rate",
        legacy_name=f"{NAME} heating rate",
        icon="mdi:chart-line",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda entity: entity.device.water_heater_heating_rate,
        system_types=[SystemType.VELIS],
        whe_types=[WheType.NuosSplit],
    ),
    # --- Errors (all devices) ---------------------------------------------------
    AristonSensorEntityDescription(
        key="errors_count",
        legacy_name=f"{NAME} errors count",
        icon="mdi:alert-circle-outline",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        coordinator=BUS_ERRORS_COORDINATOR,
        value_fn=lambda entity: len(entity.device.bus_errors),
        extra_attributes={ATTR_ERRORS: lambda entity: entity.device.bus_errors},
    ),
    # --- Energy: last month (Galevo) -------------------------------------------
    _energy_last_month(
        "gas_heating_last_month",
        f"{NAME} gas consumption for heating last month",
        lambda entity: entity.device.gas_consumption_for_heating_last_month,
    ),
    _energy_last_month(
        "electricity_heating_last_month",
        f"{NAME} electricity consumption for heating last month",
        lambda entity: entity.device.electricity_consumption_for_heating_last_month,
    ),
    _energy_last_month(
        "electricity_cooling_last_month",
        f"{NAME} electricity consumption for cooling last month",
        lambda entity: entity.device.electricity_consumption_for_cooling_last_month,
        extra_features=[DeviceAttribute.HPMP_SYS],
    ),
    _energy_last_month(
        "gas_water_last_month",
        f"{NAME} gas consumption for water last month",
        lambda entity: entity.device.gas_consumption_for_water_last_month,
        extra_features=[CustomDeviceFeatures.HAS_DHW],
    ),
    _energy_last_month(
        "electricity_water_last_month",
        f"{NAME} electricity consumption for water last month",
        lambda entity: entity.device.electricity_consumption_for_water_last_month,
        extra_features=[CustomDeviceFeatures.HAS_DHW],
    ),
    # --- Energy: running totals (any device with metering) ----------------------
    _energy_total(
        "ch_total_energy",
        f"{NAME} central heating total energy consumption",
        ConsumptionType.CENTRAL_HEATING_TOTAL_ENERGY,
        lambda entity: entity.device.central_heating_total_energy_consumption,
    ),
    _energy_total(
        "dhw_total_energy",
        f"{NAME} domestic hot water total energy consumption",
        ConsumptionType.DOMESTIC_HOT_WATER_TOTAL_ENERGY,
        lambda entity: entity.device.domestic_hot_water_total_energy_consumption,
    ),
    _energy_total(
        "ch_gas",
        f"{NAME} central heating gas consumption",
        ConsumptionType.CENTRAL_HEATING_GAS,
        lambda entity: entity.device.central_heating_gas_consumption,
    ),
    _energy_total(
        "dhw_heat_pump_electricity",
        f"{NAME} domestic hot water heating pump electricity consumption",
        ConsumptionType.DOMESTIC_HOT_WATER_HEATING_PUMP_ELECTRICITY,
        lambda entity: entity.device.domestic_hot_water_heating_pump_electricity_consumption,
    ),
    _energy_total(
        "dhw_resistor_electricity",
        f"{NAME} domestic hot water resistor electricity consumption",
        ConsumptionType.DOMESTIC_HOT_WATER_RESISTOR_ELECTRICITY,
        lambda entity: entity.device.domestic_hot_water_resistor_electricity_consumption,
    ),
    _energy_total(
        "dhw_gas",
        f"{NAME} domestic hot water gas consumption",
        ConsumptionType.DOMESTIC_HOT_WATER_GAS,
        lambda entity: entity.device.domestic_hot_water_gas_consumption,
    ),
    _energy_total(
        "ch_electricity",
        f"{NAME} central heating electricity consumption",
        ConsumptionType.CENTRAL_HEATING_ELECTRICITY,
        lambda entity: entity.device.central_heating_electricity_consumption,
    ),
    _energy_total(
        "dhw_electricity",
        f"{NAME} domestic hot water electricity consumption",
        ConsumptionType.DOMESTIC_HOT_WATER_ELECTRICITY,
        lambda entity: entity.device.domestic_hot_water_electricity_consumption,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AristonConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Ariston sensors."""
    async_add_entities(build_entities(entry, SENSOR_TYPES, AristonSensor))


class AristonSensor(AristonEntity, SensorEntity):
    """An Ariston sensor."""

    entity_description: AristonSensorEntityDescription

    def __init__(
        self,
        coordinator: AristonCoordinator,
        description: AristonSensorEntityDescription,
        zone: int = 0,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, description, zone)

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""
        return self.entity_description.value_fn(self)

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the unit, taken from the cloud when the description says so."""
        if self.entity_description.unit_fn is not None:
            return self.entity_description.unit_fn(self)
        return super().native_unit_of_measurement

    @property
    def last_reset(self) -> datetime | None:
        """Return when the total was last reset, for TOTAL sensors."""
        if self.entity_description.last_reset_fn is not None:
            return self.entity_description.last_reset_fn(self)
        return None
