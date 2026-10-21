"""Shared fixtures: a fake Ariston cloud backed by the real device classes."""

from __future__ import annotations

import copy
from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from ariston.galevo_device import AristonGalevoDevice
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.const import CONF_DEVICE, CONF_PASSWORD, CONF_USERNAME

from custom_components.ariston.const import API_URL_SETTING, API_USER_AGENT, DOMAIN

pytest_plugins = "pytest_homeassistant_custom_component"

GOOD_PASSWORD = "correct-horse"

BOILER = {
    "gw": "GW123",
    "sn": "SN123",
    "name": "Boiler",
    "sys": 3,
    "hpmpSys": False,
    "fwVer": "1.2.3",
}
SECOND_BOILER = {**BOILER, "gw": "GW456", "sn": "SN456", "name": "Cottage"}

FEATURES: dict[str, Any] = {
    "zones": [{"num": 1, "name": "Living room", "roomSens": True}],
    "hasBoiler": True,
    "dhwModeChangeable": True,
    "autoThermoReg": True,
    "hasMetering": False,
    "hybridSys": False,
}


def _item(item_id: str, value: Any, zone: int = 0, **extra: Any) -> dict[str, Any]:
    return {"id": item_id, "zone": zone, "value": value, **extra}


PROPERTIES = {
    "items": [
        _item(
            "PlantMode",
            1,
            options=[0, 1, 2, 5],
            optTexts=["Summer", "Winter", "Heating only", "Off"],
        ),
        _item("IsFlameOn", True),
        _item("Holiday", False, expiresOn=None),
        _item("HeatingCircuitPressure", 1.3, unit="bar"),
        _item("ChFlowSetpointTemp", 55, unit="°C"),
        _item("ChFlowTemp", 52.5, unit="°C"),
        _item("OutsideTemp", 7.5, unit="°C", max=50),
        _item("DhwStorageTemperature", None, max=70),
        _item("DhwTemp", 48, min=35, max=60, step=1, decimals=0, unit="°C"),
        _item(
            "DhwMode", 2, options=[0, 1, 2], optTexts=["Disabled", "Time based", "Always active"]
        ),
        _item("AutomaticThermoregulation", True),
        _item("ZoneMeasuredTemp", 20.5, zone=1, unit="°C", decimals=1),
        _item("ZoneDesiredTemp", 21, zone=1, unit="°C"),
        _item("ZoneComfortTemp", 21, zone=1, min=10, max=30, step=0.5, unit="°C"),
        _item("ZoneMode", 2, zone=1, options=[0, 2, 3]),
        _item("ZoneHeatRequest", True, zone=1),
        _item("ZoneEconomyTemp", 16, zone=1, unit="°C"),
        _item("HeatingFlowTemp", 55, zone=1, min=20, max=80, step=1, unit="°C", decimals=0),
        _item("HeatingFlowOffset", 0, zone=1, min=-5, max=5, step=1, unit="°C", decimals=0),
    ]
}

MENU_ITEMS = [{"id": 119, "value": 72, "unit": "%"}, {"id": 124, "value": 40, "unit": "°C"}]

ENTRY_DATA = {
    CONF_USERNAME: "user@example.com",
    CONF_PASSWORD: GOOD_PASSWORD,
    API_URL_SETTING: "https://www.ariston-net.remotethermo.com/api/v2/",
    API_USER_AGENT: "RestSharp/106.11.7.0",
    CONF_DEVICE: BOILER,
}


def make_api() -> MagicMock:
    """Return an API double that answers with the canned boiler data."""
    api = MagicMock()
    api.async_get_features_for_device = AsyncMock(side_effect=lambda *_: copy.deepcopy(FEATURES))
    # The device mutates the returned dict on writes, so hand out a fresh copy each poll.
    api.async_get_properties = AsyncMock(side_effect=lambda *_, **__: copy.deepcopy(PROPERTIES))
    api.async_get_menu_items = AsyncMock(return_value=MENU_ITEMS)
    api.async_get_bus_errors = AsyncMock(return_value=[])
    api.async_set_property = AsyncMock()
    api.async_set_holiday = AsyncMock()
    return api


class FakeAriston:
    """Stand-in for ``ariston.Ariston`` that never touches the network."""

    api: MagicMock = make_api()
    devices: list[dict[str, Any]] = [BOILER]

    def __init__(self) -> None:
        self.connected_with: dict[str, Any] = {}

    async def async_connect(
        self, username: str, password: str, api_url: str, user_agent: str
    ) -> bool:
        self.connected_with = {
            "username": username,
            "password": password,
            "api_url": api_url,
            "user_agent": user_agent,
        }
        return password == GOOD_PASSWORD

    async def async_discover(self) -> list[dict[str, Any]]:
        return list(self.devices)

    async def async_hello(self, gateway: str, is_metric: bool = True, language_tag: str = "en-US"):
        device = next((d for d in self.devices if d["gw"] == gateway), None)
        if device is None:
            return None
        return AristonGalevoDevice(self.api, device, is_metric, language_tag)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Allow loading custom_components/ariston."""


@pytest.fixture
def fake_api() -> Generator[MagicMock]:
    """Patch the Ariston client in both the integration and its config flow."""
    FakeAriston.api = make_api()
    FakeAriston.devices = [BOILER]
    with (
        patch("custom_components.ariston.Ariston", FakeAriston),
        patch("custom_components.ariston.config_flow.Ariston", FakeAriston),
    ):
        yield FakeAriston.api


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """A config entry for the boiler, as the config flow would create it."""
    return MockConfigEntry(domain=DOMAIN, title="Boiler", unique_id="GW123", data=ENTRY_DATA)
