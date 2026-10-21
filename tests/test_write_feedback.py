"""Writes: timeouts, clear errors, fast rechecks and pending-until-confirmed values."""

from __future__ import annotations

import asyncio
import copy
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from ariston.ariston_api import ConnectionException
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from homeassistant.components.persistent_notification import _async_get_or_create_notifications
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from .conftest import PROPERTIES

SELECT = "select.boiler_system_mode"


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED


def _cloud_reports(fake_api: MagicMock, plant_mode: int) -> None:
    """Make the fake cloud report a given plant mode on the next polls."""
    props = copy.deepcopy(PROPERTIES)
    next(i for i in props["items"] if i["id"] == "PlantMode")["value"] = plant_mode
    fake_api.async_get_properties.side_effect = lambda *_, **__: copy.deepcopy(props)


async def _select_summer(hass: HomeAssistant) -> None:
    await hass.services.async_call(
        "select", "select_option", {"entity_id": SELECT, "option": "Summer"}, blocking=True
    )


async def test_write_timeout_is_a_clear_error(
    hass: HomeAssistant, fake_api: MagicMock, config_entry
) -> None:
    """A hanging cloud call fails fast with a translated HomeAssistantError."""
    await _setup(hass, config_entry)

    async def _hang(*_args, **_kwargs):
        await asyncio.sleep(5)

    fake_api.async_set_property = AsyncMock(side_effect=_hang)
    with (
        patch("custom_components.ariston.coordinator.WRITE_TIMEOUT", timedelta(seconds=0.05)),
        pytest.raises(HomeAssistantError, match="did not answer within 0 seconds"),
    ):
        await _select_summer(hass)
    assert hass.states.get(SELECT).state == "Winter"
    assert "pending_command" not in hass.states.get(SELECT).attributes


async def test_write_failure_is_a_clear_error(
    hass: HomeAssistant, fake_api: MagicMock, config_entry
) -> None:
    """A cloud error on a write surfaces as a HomeAssistantError naming the entity."""
    await _setup(hass, config_entry)
    fake_api.async_set_property = AsyncMock(side_effect=ConnectionException(500))
    with pytest.raises(
        HomeAssistantError, match=r"rejected the command for select\.boiler_system_mode"
    ):
        await _select_summer(hass)
    assert hass.states.get(SELECT).state == "Winter"


async def test_written_value_survives_stale_polls_until_confirmed(
    hass: HomeAssistant, fake_api: MagicMock, config_entry
) -> None:
    """The written mode stays visible while the cloud still reports the old one."""
    await _setup(hass, config_entry)
    coordinator = config_entry.runtime_data.coordinator

    await _select_summer(hass)
    state = hass.states.get(SELECT)
    assert state.state == "Summer"
    assert state.attributes["pending_command"] is True
    # Other entities of the same device are not flagged.
    assert "pending_command" not in hass.states.get("climate.boiler").attributes

    # The cloud still says Winter: the entity keeps Summer and stays pending.
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(SELECT).state == "Summer"
    assert hass.states.get(SELECT).attributes["pending_command"] is True
    assert hass.states.get("climate.boiler").attributes["preset_mode"] == "Summer"

    # The cloud catches up: confirmed, flag gone.
    _cloud_reports(fake_api, 0)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(SELECT).state == "Summer"
    assert "pending_command" not in hass.states.get(SELECT).attributes


async def test_unconfirmed_write_expires_with_a_notification(
    hass: HomeAssistant, fake_api: MagicMock, config_entry, freezer
) -> None:
    """After two minutes without confirmation the cloud value wins and the user is told."""
    await _setup(hass, config_entry)
    coordinator = config_entry.runtime_data.coordinator

    await _select_summer(hass)
    freezer.tick(timedelta(minutes=3))
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    state = hass.states.get(SELECT)
    assert state.state == "Winter"
    assert "pending_command" not in state.attributes
    notifications = _async_get_or_create_notifications(hass)
    assert "ariston_unconfirmed_GW123" in notifications
    assert "select.boiler_system_mode" in notifications["ariston_unconfirmed_GW123"]["message"]


async def test_write_schedules_fast_rechecks(
    hass: HomeAssistant, fake_api: MagicMock, config_entry
) -> None:
    """A write triggers extra polls at +10 s and +40 s instead of waiting for the interval."""
    await _setup(hass, config_entry)
    polls_before = fake_api.async_get_properties.await_count

    await _select_summer(hass)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=12))
    await hass.async_block_till_done()
    assert fake_api.async_get_properties.await_count == polls_before + 1

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=42))
    await hass.async_block_till_done()
    assert fake_api.async_get_properties.await_count == polls_before + 2


async def test_read_timeout_marks_unavailable(
    hass: HomeAssistant, fake_api: MagicMock, config_entry
) -> None:
    """A hanging poll does not block forever; entities become unavailable."""
    await _setup(hass, config_entry)
    coordinator = config_entry.runtime_data.coordinator

    async def _hang(*_args, **_kwargs):
        await asyncio.sleep(5)

    fake_api.async_get_properties.side_effect = _hang
    with patch("custom_components.ariston.coordinator.READ_TIMEOUT", timedelta(seconds=0.05)):
        await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator.last_update_success is False
    assert hass.states.get(SELECT).state == "unavailable"
