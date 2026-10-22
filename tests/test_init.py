"""Tests for setup, entities, services and diagnostics with a Galevo boiler."""

from __future__ import annotations

import copy
from unittest.mock import AsyncMock, MagicMock

import pytest
from ariston.ariston_api import ConnectionException
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.ariston.const import DOMAIN

from .conftest import PROPERTIES


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED


async def test_entities_and_states(
    hass: HomeAssistant, fake_api: MagicMock, config_entry: MockConfigEntry
) -> None:
    """The boiler produces the expected entities with device-prefixed names."""
    await _setup(hass, config_entry)

    assert hass.states.get("climate.boiler").state == "heat"
    assert hass.states.get("climate.boiler").attributes["current_temperature"] == 20.5
    assert hass.states.get("climate.boiler").attributes["preset_mode"] == "Winter"
    assert hass.states.get("climate.boiler").attributes["heat_request"] is True

    assert hass.states.get("water_heater.boiler").attributes["temperature"] == 48
    assert hass.states.get("water_heater.boiler").attributes["operation_mode"] == "Always active"

    assert hass.states.get("sensor.boiler_heating_circuit_pressure").state == "1.3"
    assert (
        hass.states.get("sensor.boiler_heating_circuit_pressure").attributes["unit_of_measurement"]
        == "bar"
    )
    assert hass.states.get("sensor.boiler_hot_water_temperature").state == "48"
    assert hass.states.get("sensor.boiler_outside_temperature").state == "7.5"
    assert hass.states.get("sensor.boiler_signal_strength").state == "72"
    assert hass.states.get("sensor.boiler_heating_return_temperature").state == "40"
    assert hass.states.get("sensor.boiler_error_count").state == "0"

    assert hass.states.get("binary_sensor.boiler_flame").state == STATE_ON
    assert hass.states.get("binary_sensor.boiler_problem").state == STATE_OFF
    assert hass.states.get("binary_sensor.boiler_holiday_mode").state == STATE_OFF
    # Zone entities carry the zone name from the Ariston app.
    assert hass.states.get("binary_sensor.boiler_living_room_heat_request").state == STATE_ON
    assert hass.states.get("sensor.boiler_living_room_economy_temperature").state == "16"
    assert hass.states.get("number.boiler_living_room_heating_flow_temperature").state == "55.0"

    system_mode = hass.states.get("select.boiler_system_mode")
    assert system_mode.state == "Winter"
    assert system_mode.attributes["options"] == ["Summer", "Winter", "Heating only", "Off"]
    assert hass.states.get("switch.boiler_automatic_thermoregulation").state == STATE_ON

    # Not applicable to this boiler: no metering, no hybrid system, no Velis entities.
    assert hass.states.get("sensor.boiler_heating_energy") is None
    assert hass.states.get("select.boiler_hybrid_mode") is None
    assert hass.states.get("switch.boiler_power") is None


async def test_unique_ids_are_backwards_compatible(
    hass: HomeAssistant, fake_api: MagicMock, config_entry: MockConfigEntry
) -> None:
    """Entities keep the unique ids of the 0.x releases; new ones use the key."""
    await _setup(hass, config_entry)
    registry = er.async_get(hass)

    expected = {
        "climate.boiler": "GW123_1",
        "water_heater.boiler": "GW123-water_heater",
        "sensor.boiler_heating_circuit_pressure": "GW123-Ariston heating circuit pressure",
        "sensor.boiler_outside_temperature": "GW123-Ariston Outside temp",
        "sensor.boiler_error_count": "GW123-Ariston errors count",
        "binary_sensor.boiler_flame": "GW123-Ariston is flame on",
        "switch.boiler_automatic_thermoregulation": "GW123-Ariston automatic thermoregulation",
        "number.boiler_living_room_heating_flow_temperature": "GW123-Ariston heating flow temperature 1-1",
        "number.boiler_living_room_heating_flow_offset": "GW123-Ariston heating flow offset 1-1",
        # new in 1.0
        "select.boiler_system_mode": "GW123-plant_mode",
        "binary_sensor.boiler_problem": "GW123-problem",
        "binary_sensor.boiler_living_room_heat_request": "GW123-zone_heat_request-1",
        "sensor.boiler_hot_water_temperature": "GW123-hot_water_temperature",
    }
    for entity_id, unique_id in expected.items():
        entry = registry.async_get(entity_id)
        assert entry is not None, entity_id
        assert entry.unique_id == unique_id, entity_id

    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, "SN123")})
    assert device is not None
    assert device.manufacturer == "Ariston"
    assert device.serial_number == "SN123"
    assert device.sw_version == "1.2.3"


async def test_select_and_switch_write_through(
    hass: HomeAssistant, fake_api: MagicMock, config_entry: MockConfigEntry
) -> None:
    """Writes go to the cloud and the optimistic state reaches every entity."""
    await _setup(hass, config_entry)

    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.boiler_system_mode", "option": "Summer"},
        blocking=True,
    )
    assert fake_api.async_set_property.await_count == 1
    assert hass.states.get("select.boiler_system_mode").state == "Summer"
    # The climate preset reflects the same plant mode without another cloud poll.
    assert hass.states.get("climate.boiler").attributes["preset_mode"] == "Summer"

    await hass.services.async_call(
        "switch",
        "turn_off",
        {"entity_id": "switch.boiler_automatic_thermoregulation"},
        blocking=True,
    )
    assert hass.states.get("switch.boiler_automatic_thermoregulation").state == STATE_OFF


async def test_services(
    hass: HomeAssistant, fake_api: MagicMock, config_entry: MockConfigEntry
) -> None:
    """create_vacation and set_item_by_id resolve the device and validate input."""
    await _setup(hass, config_entry)
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, "SN123")})

    await hass.services.async_call(
        DOMAIN, "create_vacation", {"device_id": device.id, "end_date": "2026-12-24"}, blocking=True
    )
    fake_api.async_set_holiday.assert_awaited_once_with("GW123", "2026-12-24T00:00:00")
    assert hass.states.get("binary_sensor.boiler_holiday_mode").state == STATE_ON

    await hass.services.async_call(
        DOMAIN,
        "set_item_by_id",
        {"device_id": device.id, "item_id": "ZoneComfortTemp", "zone": 1, "value": 19},
        blocking=True,
    )
    assert fake_api.async_set_property.await_count == 1

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "create_vacation", {"device_id": "does-not-exist"}, blocking=True
        )


async def test_diagnostics_redact_identifiers(
    hass: HomeAssistant,
    fake_api: MagicMock,
    config_entry: MockConfigEntry,
    hass_client: ClientSessionGenerator,
) -> None:
    """Diagnostics contain the cloud payload but not credentials or identifiers."""
    await _setup(hass, config_entry)
    diagnostics = await get_diagnostics_for_config_entry(hass, hass_client, config_entry)

    assert diagnostics["entry"]["data"]["password"] == "**REDACTED**"
    assert diagnostics["entry"]["data"]["device"]["gw"] == "**REDACTED**"
    assert diagnostics["device"]["attributes"]["sn"] == "**REDACTED**"
    assert diagnostics["device"]["system_type"] == "GALEVO"
    assert diagnostics["device"]["data"] == PROPERTIES
    assert diagnostics["coordinators"]["coordinator"]["last_update_success"] is True


async def test_cloud_error_marks_unavailable_then_recovers(
    hass: HomeAssistant, fake_api: MagicMock, config_entry: MockConfigEntry
) -> None:
    """A transient cloud error makes entities unavailable; the next poll restores them."""
    await _setup(hass, config_entry)
    coordinator = config_entry.runtime_data.coordinator

    fake_api.async_get_properties.side_effect = ConnectionException(503)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator.last_update_success is False
    assert hass.states.get("sensor.boiler_heating_circuit_pressure").state == "unavailable"
    assert hass.states.get("climate.boiler").state == "unavailable"

    fake_api.async_get_properties.side_effect = lambda *_, **__: copy.deepcopy(PROPERTIES)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get("sensor.boiler_heating_circuit_pressure").state == "1.3"
    assert hass.states.get("climate.boiler").state == "heat"


async def test_rejected_credentials_start_reauth(
    hass: HomeAssistant, fake_api: MagicMock, config_entry: MockConfigEntry
) -> None:
    """An auth error from the cloud puts the entry into the reauth state."""
    fake_api.async_get_properties.side_effect = ConnectionException("Invalid token")
    config_entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.SETUP_ERROR
    assert any(
        flow["context"].get("source") == "reauth"
        for flow in hass.config_entries.flow.async_progress()
    )


async def test_unload(
    hass: HomeAssistant, fake_api: MagicMock, config_entry: MockConfigEntry
) -> None:
    """The entry unloads cleanly."""
    await _setup(hass, config_entry)
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.NOT_LOADED
    assert hass.states.get("climate.boiler").state == "unavailable"


async def test_fault_list_outage_does_not_block_setup(
    hass: HomeAssistant, fake_api: MagicMock, config_entry: MockConfigEntry
) -> None:
    """The cloud answering the fault list with HTTP 500 leaves the device usable."""
    fake_api.async_get_bus_errors = AsyncMock(side_effect=ConnectionException(500))
    await _setup(hass, config_entry)

    assert hass.states.get("climate.boiler").state == "heat"
    assert hass.states.get("water_heater.boiler").attributes["temperature"] == 48
    assert hass.states.get("binary_sensor.boiler_problem").state == "unavailable"
    assert hass.states.get("sensor.boiler_error_count").state == "unavailable"

    # The endpoint recovers: the fault sensors come back on the next poll.
    fake_api.async_get_bus_errors = AsyncMock(return_value=[])
    await config_entry.runtime_data.coordinators["bus_errors_coordinator"].async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.boiler_problem").state == STATE_OFF
    assert hass.states.get("sensor.boiler_error_count").state == "0"


async def test_device_state_is_still_required(
    hass: HomeAssistant, fake_api: MagicMock, config_entry: MockConfigEntry
) -> None:
    """Without the device state nothing works, so setup is retried."""
    fake_api.async_get_properties.side_effect = ConnectionException(500)
    config_entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_auth_error_on_fault_list_still_starts_reauth(
    hass: HomeAssistant, fake_api: MagicMock, config_entry: MockConfigEntry
) -> None:
    """Rejected credentials are not swallowed by the optional-data handling."""
    fake_api.async_get_bus_errors = AsyncMock(side_effect=ConnectionException("Invalid token"))
    config_entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.SETUP_ERROR
    assert any(
        flow["context"].get("source") == "reauth"
        for flow in hass.config_entries.flow.async_progress()
    )
