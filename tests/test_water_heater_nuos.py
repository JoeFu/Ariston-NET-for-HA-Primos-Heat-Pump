"""Water heater behaviour on a Velis Nuos Split (Primos): off mode and per-mode limits."""

from __future__ import annotations

import copy
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from ariston.nuos_split_device import AristonNuosSplitDevice
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_DEVICE
from homeassistant.core import HomeAssistant

from custom_components.ariston.const import DOMAIN

from .conftest import ENTRY_DATA, GOOD_PASSWORD

# Shape of the real cloud payload for a Nuos Split (taken from a diagnostics download).
NUOS = {
    "gw": "GW900",
    "sn": "SN900",
    "name": "Hot Water",
    "sys": 4,
    "wheType": 4,
    "wheModelType": 11,
}
NUOS_FEATURES: dict[str, Any] = {
    "zones": [],
    "hasMetering": True,
    "dhwModeChangeable": True,
    "dhwBoilerPresent": True,
    "preHeatingSupported": True,
    "hasSlp": True,
}
NUOS_DATA = {
    "gw": "GW900",
    "on": False,
    "mode": 2,
    "waterTemp": 65,
    "comfortTemp": 65,
    "reducedTemp": 40,
    "procReqTemp": 65,
    "opMode": 1,  # COMFORT
    "boostOn": False,
    "hpState": 1,
}
NUOS_SETTINGS = {
    "SlpMaxGreenTemperature": 60,
    "SlpMaxSetpointTemperature": 70,
    "SlpMaxSetpointTemperatureMin": 60,
    "SlpMaxSetpointTemperatureMax": 70,
    "SlpMinSetpointTemperature": 40,
    "SlpMinSetpointTemperatureMin": 40,
    "SlpMinSetpointTemperatureMax": 50,
    "SlpAntilegionellaOnOff": 1,
    "SlpPreHeatingOnOff": 0,
    "SlpHeatingRate": 8,
    "SlpPermanentBoostOnOff": 0,
    "SlpNightModeOnOff": 0,
    "SlpNightBeginAsMinutes": 5888,
    "SlpNightEndAsMinutes": 1536,
}
NUOS_CONSUMPTIONS = [
    {"k": 8, "p": 1, "v": [0, 1.138, 1.083, 0]},
    {"k": 9, "p": 1, "v": [0, 0.538, 0.019, 0]},
]


class FakeNuosAriston:
    """Ariston client double that hands out a real AristonNuosSplitDevice."""

    api: MagicMock

    async def async_connect(
        self, username: str, password: str, api_url: str, user_agent: str
    ) -> bool:
        return password == GOOD_PASSWORD

    async def async_discover(self) -> list[dict[str, Any]]:
        return [NUOS]

    async def async_hello(self, gateway: str, is_metric: bool = True, language_tag: str = "en-US"):
        return AristonNuosSplitDevice(self.api, NUOS)


@pytest.fixture
def nuos_api() -> MagicMock:
    """Patch the client and return the API double so tests can inspect writes."""
    api = MagicMock()
    api.async_get_features_for_device = AsyncMock(
        side_effect=lambda *_: copy.deepcopy(NUOS_FEATURES)
    )
    api.async_get_velis_plant_data = AsyncMock(side_effect=lambda *_: copy.deepcopy(NUOS_DATA))
    api.async_get_velis_plant_settings = AsyncMock(
        side_effect=lambda *_: copy.deepcopy(NUOS_SETTINGS)
    )
    api.async_get_consumptions_sequences = AsyncMock(
        side_effect=lambda *_: copy.deepcopy(NUOS_CONSUMPTIONS)
    )
    api.async_get_bus_errors = AsyncMock(return_value=[])
    api.async_set_velis_power = AsyncMock()
    api.async_set_nuos_mode = AsyncMock()
    api.async_set_nuos_temperature = AsyncMock()
    api.async_set_velis_plant_setting = AsyncMock()
    FakeNuosAriston.api = api
    with patch("custom_components.ariston.Ariston", FakeNuosAriston):
        yield api


@pytest.fixture
async def nuos_entry(hass: HomeAssistant, nuos_api: MagicMock) -> MockConfigEntry:
    """A loaded config entry for the Nuos Split."""
    entry = MockConfigEntry(
        domain=DOMAIN, title="Hot Water", unique_id="GW900", data={**ENTRY_DATA, CONF_DEVICE: NUOS}
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    return entry


WH = "water_heater.hot_water"


async def test_off_appears_as_an_operation_mode(
    hass: HomeAssistant, nuos_api: MagicMock, nuos_entry
) -> None:
    """A switched-off heater reports "off"; the mode list offers it first."""
    state = hass.states.get(WH)
    assert state.state == "off"
    assert state.attributes["operation_list"] == ["off", "green", "comfort", "fast", "imemory"]
    assert state.attributes["temperature"] == 65
    assert state.attributes["current_temperature"] == 65
    # Limits follow the installer settings (40-70) narrowed per mode.
    assert state.attributes["temperature_limits"] == {
        "green": [40.0, 60.0],
        "comfort": [40.0, 70.0],
        "fast": [40.0, 70.0],
        "imemory": [50.0, 70.0],
    }


async def test_selecting_a_mode_powers_on(
    hass: HomeAssistant, nuos_api: MagicMock, nuos_entry
) -> None:
    """Choosing COMFORT while off switches the heater on and sets the mode."""
    await hass.services.async_call(
        "water_heater",
        "set_operation_mode",
        {"entity_id": WH, "operation_mode": "comfort"},
        blocking=True,
    )
    nuos_api.async_set_velis_power.assert_awaited_once()
    assert nuos_api.async_set_velis_power.await_args.args[1:] == ("GW900", True)
    nuos_api.async_set_nuos_mode.assert_awaited_once()
    assert hass.states.get(WH).state == "comfort"
    assert hass.states.get(WH).attributes["min_temp"] == 40
    assert hass.states.get(WH).attributes["max_temp"] == 70

    await hass.services.async_call(
        "water_heater",
        "set_operation_mode",
        {"entity_id": WH, "operation_mode": "off"},
        blocking=True,
    )
    assert nuos_api.async_set_velis_power.await_args.args[1:] == ("GW900", False)
    assert hass.states.get(WH).state == "off"


async def test_green_mode_limits_the_setpoint(
    hass: HomeAssistant, nuos_api: MagicMock, nuos_entry
) -> None:
    """Switching to GREEN with a 65 °C target first lowers it to the 60 °C heat-pump ceiling."""
    await hass.services.async_call(
        "water_heater",
        "set_operation_mode",
        {"entity_id": WH, "operation_mode": "green"},
        blocking=True,
    )
    comfort, reduced = nuos_api.async_set_nuos_temperature.await_args.args[1:3]
    assert (comfort, reduced) == (60, 40)
    state = hass.states.get(WH)
    assert state.state == "green"
    assert state.attributes["max_temp"] == 60
    assert state.attributes["min_temp"] == 40

    # In GREEN a request for 70 °C is clamped to 60 °C.
    nuos_api.async_set_nuos_temperature.reset_mock()
    await hass.services.async_call(
        "water_heater", "set_temperature", {"entity_id": WH, "temperature": 70}, blocking=True
    )
    assert nuos_api.async_set_nuos_temperature.await_args.args[1] == 60


async def test_imemory_has_a_floor(hass: HomeAssistant, nuos_api: MagicMock, nuos_entry) -> None:
    """i-Memory keeps the comfort temperature at or above 50 °C."""
    await hass.services.async_call(
        "water_heater",
        "set_operation_mode",
        {"entity_id": WH, "operation_mode": "imemory"},
        blocking=True,
    )
    assert hass.states.get(WH).attributes["min_temp"] == 50
    await hass.services.async_call(
        "water_heater", "set_temperature", {"entity_id": WH, "temperature": 45}, blocking=True
    )
    assert nuos_api.async_set_nuos_temperature.await_args.args[1] == 50


async def test_green_ceiling_follows_the_cloud_setting(
    hass: HomeAssistant, nuos_api: MagicMock, nuos_entry
) -> None:
    """Raising the installer's GREEN ceiling through the number entity widens the GREEN range."""
    number = hass.states.get("number.hot_water_maximum_green_mode_temperature")
    assert number.state == "60.0"
    assert number.attributes["min"] == 40
    assert number.attributes["max"] == 60

    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.hot_water_maximum_green_mode_temperature", "value": 55},
        blocking=True,
    )
    nuos_api.async_set_velis_plant_setting.assert_awaited_once()
    assert nuos_api.async_set_velis_plant_setting.await_args.args[2:] == (
        "SlpMaxGreenTemperature",
        55,
        60,
    )
    assert hass.states.get(WH).attributes["temperature_limits"]["green"] == [40.0, 55.0]


async def test_target_temperature_updates_immediately(
    hass: HomeAssistant, nuos_api: MagicMock, nuos_entry
) -> None:
    """The dial shows the new target right away instead of jumping back until the next poll."""
    await hass.services.async_call(
        "water_heater",
        "set_operation_mode",
        {"entity_id": WH, "operation_mode": "comfort"},
        blocking=True,
    )
    await hass.services.async_call(
        "water_heater", "set_temperature", {"entity_id": WH, "temperature": 58}, blocking=True
    )
    state = hass.states.get(WH)
    assert state.attributes["temperature"] == 58
    assert state.attributes["pending_command"] is True
    # A stale poll (cloud still says 65) does not undo it.
    await nuos_entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(WH).attributes["temperature"] == 58


async def test_other_nuos_entities(hass: HomeAssistant, nuos_api: MagicMock, nuos_entry) -> None:
    """Sanity check of the remaining Nuos entities against the real payload shape."""
    assert hass.states.get("sensor.hot_water_water_temperature").state == "65"
    assert hass.states.get("sensor.hot_water_heating_rate").state == "8"
    assert hass.states.get("switch.hot_water_power").state == "off"
    assert hass.states.get("switch.hot_water_anti_legionella").state == "on"
    assert (
        hass.states.get("sensor.hot_water_hot_water_heat_pump_electricity_total").state == "2.221"
    )
    assert (
        hass.states.get("sensor.hot_water_hot_water_heat_pump_electricity_last_24_h").state
        == "2.221"
    )
    assert hass.states.get("binary_sensor.hot_water_problem").state == "off"


async def test_night_function(hass: HomeAssistant, nuos_api: MagicMock, nuos_entry) -> None:
    """Night mode switch and window come from the Slp plant settings, clock encoded as h*256+m."""
    assert hass.states.get("switch.hot_water_night_mode").state == "off"
    assert hass.states.get("switch.hot_water_permanent_boost").state == "off"
    assert hass.states.get("time.hot_water_night_mode_start").state == "23:00:00"
    assert hass.states.get("time.hot_water_night_mode_end").state == "06:00:00"

    await hass.services.async_call(
        "time",
        "set_value",
        {"entity_id": "time.hot_water_night_mode_start", "time": "22:30:00"},
        blocking=True,
    )
    assert nuos_api.async_set_velis_plant_setting.await_args.args[2:] == (
        "SlpNightBeginAsMinutes",
        22 * 256 + 30,
        5888,
    )
    assert hass.states.get("time.hot_water_night_mode_start").state == "22:30:00"

    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": "switch.hot_water_night_mode"}, blocking=True
    )
    assert nuos_api.async_set_velis_plant_setting.await_args.args[2:] == (
        "SlpNightModeOnOff",
        True,
        0,
    )
    assert hass.states.get("switch.hot_water_night_mode").state == "on"


async def test_device_model_is_the_commercial_name(
    hass: HomeAssistant, nuos_api: MagicMock, nuos_entry
) -> None:
    """The Primos is shown as product name plus product code."""
    from homeassistant.helpers import device_registry as dr

    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, "SN900")})
    assert device.model == "Primos 205"
    assert device.model_id == "ARIHPWH-200"


async def test_energy_total_accumulates_across_window_shifts(
    hass: HomeAssistant, nuos_api: MagicMock, nuos_entry
) -> None:
    """Buckets that scroll out of the cloud's 24 h window are kept in the running total."""
    total = "sensor.hot_water_hot_water_heat_pump_electricity_total"
    coordinator = nuos_entry.runtime_data.coordinators["energy_coordinator"]
    assert hass.states.get(total).state == "2.221"  # 0 + 1.138 + 1.083 + 0

    def cloud(window: list[float]) -> None:
        nuos_api.async_get_consumptions_sequences.side_effect = lambda *_: [
            {"k": 8, "p": 1, "v": window},
            {"k": 9, "p": 1, "v": [0, 0.538, 0.019, 0]},
        ]

    # The current hour grows: no shift, the total follows.
    cloud([0, 1.138, 1.083, 0.4])
    await coordinator.async_refresh()
    assert hass.states.get(total).state == "2.621"

    # One hour later the window moved by one bucket (a 0 scrolled out).
    cloud([1.138, 1.083, 0.4, 0.5])
    await coordinator.async_refresh()
    assert hass.states.get(total).state == "3.121"

    # Two hours later: 1.138 and 1.083 scrolled out and must stay counted.
    cloud([0.4, 0.5, 0.2, 0])
    await coordinator.async_refresh()
    assert hass.states.get(total).state == "3.321"
    assert hass.states.get(total).attributes["last_24h"] == 1.1


def test_detect_shift() -> None:
    """Shift detection prefers the smallest move that keeps completed buckets identical."""
    from custom_components.ariston.sensor import detect_shift

    assert detect_shift([0, 1, 2, 3], [0, 1, 2, 9]) == 0
    assert detect_shift([0, 1, 2, 3], [1, 2, 3, 4]) == 1
    assert detect_shift([0, 1, 2, 3], [2, 3, 7, 8]) == 2
    assert detect_shift([0, 1, 2, 3], [5, 6, 7, 8]) == 4  # nothing recognisable: all scrolled out
    assert detect_shift([0, 0, 0, 0], [0, 0, 0, 0]) == 0
