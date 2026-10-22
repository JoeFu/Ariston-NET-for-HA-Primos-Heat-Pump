"""Sensors for Ariston devices."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ariston.const import (
    ConsumptionTimeInterval,
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
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import ExtraStoredData, RestoreEntity

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

    value_fn: Callable[[AristonSensor], Any] | None = None
    unit_fn: Callable[[AristonSensor], str | None] | None = None
    last_reset_fn: Callable[[AristonSensor], datetime | None] | None = None
    # For energy sensors: which cloud consumption sequence feeds the entity.
    consumption_type: ConsumptionType | None = None


def _sequence(
    device: Any, consumption_type: ConsumptionType, interval: ConsumptionTimeInterval
) -> list[float] | None:
    """Return one consumption sequence from the cloud (None when the device lacks it)."""
    for sequence in device.consumptions_sequences or []:
        if sequence.get("k") == consumption_type.value and sequence.get("p") == interval.value:
            values = sequence.get("v") or []
            try:
                return [float(v) for v in values]
            except (TypeError, ValueError):
                return None
    return None


def _energy_total(
    key: str,
    legacy_name: str,
    consumption_type: ConsumptionType,
    *,
    system_types: list[SystemType] | None = None,
) -> AristonSensorEntityDescription:
    """Describe an accumulated energy total built from the cloud's hourly buckets."""
    return AristonSensorEntityDescription(
        key=key,
        legacy_name=legacy_name,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=3,
        coordinator=ENERGY_COORDINATOR,
        device_features=[DeviceFeatures.HAS_METERING, consumption_type.name],
        system_types=system_types,
        consumption_type=consumption_type,
    )


def _energy_last_24h(key: str, consumption_type: ConsumptionType) -> AristonSensorEntityDescription:
    """Describe the energy used over the cloud's last 24 hourly buckets.

    A rolling window is neither a measurement nor a running total, so it has no state
    class (HA rejects ``measurement`` for energy sensors). Use the ``... total`` sensors
    for statistics and the Energy dashboard.
    """
    return AristonSensorEntityDescription(
        key=key,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=3,
        coordinator=ENERGY_COORDINATOR,
        device_features=[DeviceFeatures.HAS_METERING, consumption_type.name],
        value_fn=lambda entity: _last_24h(entity.device, consumption_type),
    )


def _last_24h(device: Any, consumption_type: ConsumptionType) -> float | None:
    window = _sequence(device, consumption_type, ConsumptionTimeInterval.LAST_DAY)
    return round(sum(window), 3) if window is not None else None


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
    # --- Energy: accumulated totals (any device with metering) -------------------
    _energy_total(
        "ch_total_energy",
        f"{NAME} central heating total energy consumption",
        ConsumptionType.CENTRAL_HEATING_TOTAL_ENERGY,
    ),
    _energy_total(
        "dhw_total_energy",
        f"{NAME} domestic hot water total energy consumption",
        ConsumptionType.DOMESTIC_HOT_WATER_TOTAL_ENERGY,
    ),
    _energy_total(
        "ch_gas",
        f"{NAME} central heating gas consumption",
        ConsumptionType.CENTRAL_HEATING_GAS,
    ),
    _energy_total(
        "dhw_heat_pump_electricity",
        f"{NAME} domestic hot water heating pump electricity consumption",
        ConsumptionType.DOMESTIC_HOT_WATER_HEATING_PUMP_ELECTRICITY,
    ),
    _energy_total(
        "dhw_resistor_electricity",
        f"{NAME} domestic hot water resistor electricity consumption",
        ConsumptionType.DOMESTIC_HOT_WATER_RESISTOR_ELECTRICITY,
    ),
    _energy_total(
        "dhw_gas",
        f"{NAME} domestic hot water gas consumption",
        ConsumptionType.DOMESTIC_HOT_WATER_GAS,
    ),
    _energy_total(
        "ch_electricity",
        f"{NAME} central heating electricity consumption",
        ConsumptionType.CENTRAL_HEATING_ELECTRICITY,
    ),
    _energy_total(
        "dhw_electricity",
        f"{NAME} domestic hot water electricity consumption",
        ConsumptionType.DOMESTIC_HOT_WATER_ELECTRICITY,
    ),
    # --- Energy: last 24 hours ---------------------------------------------------
    _energy_last_24h("ch_total_energy_last_24h", ConsumptionType.CENTRAL_HEATING_TOTAL_ENERGY),
    _energy_last_24h("dhw_total_energy_last_24h", ConsumptionType.DOMESTIC_HOT_WATER_TOTAL_ENERGY),
    _energy_last_24h("ch_gas_last_24h", ConsumptionType.CENTRAL_HEATING_GAS),
    _energy_last_24h(
        "dhw_heat_pump_electricity_last_24h",
        ConsumptionType.DOMESTIC_HOT_WATER_HEATING_PUMP_ELECTRICITY,
    ),
    _energy_last_24h(
        "dhw_resistor_electricity_last_24h", ConsumptionType.DOMESTIC_HOT_WATER_RESISTOR_ELECTRICITY
    ),
    _energy_last_24h("dhw_gas_last_24h", ConsumptionType.DOMESTIC_HOT_WATER_GAS),
    _energy_last_24h("ch_electricity_last_24h", ConsumptionType.CENTRAL_HEATING_ELECTRICITY),
    _energy_last_24h("dhw_electricity_last_24h", ConsumptionType.DOMESTIC_HOT_WATER_ELECTRICITY),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AristonConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Ariston sensors."""
    async_add_entities(build_entities(entry, SENSOR_TYPES, _make_sensor))


def _make_sensor(
    coordinator: AristonCoordinator, description: AristonSensorEntityDescription, zone: int
) -> AristonSensor:
    if description.consumption_type is not None:
        return AristonEnergyTotalSensor(coordinator, description, zone)
    return AristonSensor(coordinator, description, zone)


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
        if self.entity_description.value_fn is None:
            return None
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


def detect_shift(old: list[float], new: list[float]) -> int:
    """Return how many buckets the rolling window moved between two polls.

    The cloud's "last day" sequence is a window of 24 hourly buckets ending with the
    current, still growing hour. Buckets that were already complete keep their exact
    values, so the smallest shift ``k`` with ``old[k:-1] == new[:len-1-k]`` is the move.
    """
    size = len(old)
    if size != len(new):
        return size
    # k == size - 1 would compare empty slices and prove nothing, so it counts as "all out".
    for k in range(size - 1):
        if old[k : size - 1] == new[: size - 1 - k]:
            return k
    return size


@dataclass
class EnergyTotalData(ExtraStoredData):
    """What the accumulated total needs to survive a restart."""

    committed: float
    window: list[float] | None

    def as_dict(self) -> dict[str, Any]:
        """Serialize."""
        return {"committed": self.committed, "window": self.window}


class AristonEnergyTotalSensor(AristonSensor, RestoreEntity):
    """Energy accumulated from the cloud's rolling 24-hour window.

    The cloud only reports hourly buckets for the last day. The sensor keeps the sum of
    every bucket that has scrolled out of that window ("committed") and adds the buckets
    still in it, which gives a total that only grows (apart from the cloud correcting a
    bucket), usable in the Energy dashboard.
    """

    _committed: float = 0.0
    _window: list[float] | None = None
    _total: float | None = None

    async def async_added_to_hass(self) -> None:
        """Restore the committed energy and the last seen window."""
        await super().async_added_to_hass()
        if (stored := await self.async_get_last_extra_data()) is not None:
            data = stored.as_dict()
            try:
                self._committed = float(data.get("committed", 0.0))
            except (TypeError, ValueError):
                self._committed = 0.0
            window = data.get("window")
            self._window = [float(v) for v in window] if isinstance(window, list) else None
        self._refresh_total()

    @property
    def extra_restore_state_data(self) -> EnergyTotalData:
        """Persist the committed energy and the last seen window."""
        return EnergyTotalData(self._committed, self._window)

    @callback
    def _handle_coordinator_update(self) -> None:
        self._refresh_total()
        super()._handle_coordinator_update()

    def _refresh_total(self) -> None:
        assert self.entity_description.consumption_type is not None
        window = _sequence(
            self.device, self.entity_description.consumption_type, ConsumptionTimeInterval.LAST_DAY
        )
        if window is None:
            return
        if self._window is not None:
            shift = detect_shift(self._window, window)
            self._committed += sum(self._window[:shift])
        self._window = list(window)
        self._total = round(self._committed + sum(window), 3)

    @property
    def native_value(self) -> float | None:
        """Return the accumulated energy."""
        return self._total

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Expose the last 24 hours for convenience."""
        attributes = dict(super().extra_state_attributes or {})
        if self._window is not None:
            attributes["last_24h"] = round(sum(self._window), 3)
        return attributes or None
