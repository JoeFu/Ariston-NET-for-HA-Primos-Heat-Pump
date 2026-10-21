"""Tests for the Ariston config, reauth and options flows."""

from __future__ import annotations

from unittest.mock import MagicMock

from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant import config_entries
from homeassistant.const import CONF_DEVICE, CONF_PASSWORD, CONF_SCAN_INTERVAL, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.ariston.const import (
    API_URL_SETTING,
    API_USER_AGENT,
    BUS_ERRORS_SCAN_INTERVAL,
    DOMAIN,
    ENERGY_SCAN_INTERVAL,
)

from .conftest import BOILER, GOOD_PASSWORD, SECOND_BOILER, FakeAriston

CREDENTIALS = {CONF_USERNAME: "user@example.com", CONF_PASSWORD: GOOD_PASSWORD}


async def test_user_flow_single_device(hass: HomeAssistant, fake_api: MagicMock) -> None:
    """One device on the account: the entry is created right after the credentials."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    # Advanced-only fields stay hidden by default.
    assert API_URL_SETTING not in str(result["data_schema"].schema)

    result = await hass.config_entries.flow.async_configure(result["flow_id"], CREDENTIALS)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Boiler"
    assert result["result"].unique_id == "GW123"
    assert result["data"][CONF_DEVICE] == BOILER
    assert result["data"][API_URL_SETTING].startswith("https://")
    assert result["data"][API_USER_AGENT]


async def test_user_flow_invalid_auth_then_success(
    hass: HomeAssistant, fake_api: MagicMock
) -> None:
    """A wrong password shows a translated error and lets the user retry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**CREDENTIALS, CONF_PASSWORD: "nope"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}

    result = await hass.config_entries.flow.async_configure(result["flow_id"], CREDENTIALS)
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_multiple_devices(hass: HomeAssistant, fake_api: MagicMock) -> None:
    """Several devices: a dropdown lists them and already configured ones are hidden."""
    FakeAriston.devices = [BOILER, SECOND_BOILER]
    MockConfigEntry(domain=DOMAIN, unique_id="GW123", data={}).add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], CREDENTIALS)
    # Only the cottage is left to pick, so the flow goes straight to creating it.
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Cottage"
    assert result["result"].unique_id == "GW456"


async def test_user_flow_select_step(hass: HomeAssistant, fake_api: MagicMock) -> None:
    """With two unconfigured devices the user picks one."""
    FakeAriston.devices = [BOILER, SECOND_BOILER]
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], CREDENTIALS)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "select"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"select_device": "GW456"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_DEVICE] == SECOND_BOILER


async def test_user_flow_all_configured(hass: HomeAssistant, fake_api: MagicMock) -> None:
    """Every device already set up: abort with the standard message."""
    MockConfigEntry(domain=DOMAIN, unique_id="GW123", data={}).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], CREDENTIALS)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_user_flow_no_devices(hass: HomeAssistant, fake_api: MagicMock) -> None:
    """An account without devices aborts with a translated reason (was a raw key before)."""
    FakeAriston.devices = []
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], CREDENTIALS)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_devices_found"


async def test_reauth_flow(
    hass: HomeAssistant, fake_api: MagicMock, config_entry: MockConfigEntry
) -> None:
    """Reauth asks for credentials, stores the new password and reloads."""
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    result = await config_entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_USERNAME: "user@example.com", CONF_PASSWORD: "nope"}
    )
    assert result["errors"] == {"base": "invalid_auth"}

    result = await hass.config_entries.flow.async_configure(result["flow_id"], CREDENTIALS)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert config_entry.data[CONF_PASSWORD] == GOOD_PASSWORD
    assert config_entry.data[CONF_DEVICE] == BOILER


async def test_options_flow(
    hass: HomeAssistant, fake_api: MagicMock, config_entry: MockConfigEntry
) -> None:
    """Options store integer polling intervals."""
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_SCAN_INTERVAL: 300.0, ENERGY_SCAN_INTERVAL: 30.0, BUS_ERRORS_SCAN_INTERVAL: 900.0},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert config_entry.options == {
        CONF_SCAN_INTERVAL: 300,
        ENERGY_SCAN_INTERVAL: 30,
        BUS_ERRORS_SCAN_INTERVAL: 900,
    }
