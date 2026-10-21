"""Constants for the Ariston integration."""

from __future__ import annotations

from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "ariston"
NAME: Final = "Ariston"
MANUFACTURER: Final = "Ariston"
CONFIGURATION_URL: Final = "https://www.ariston-net.remotethermo.com"

PLATFORMS: Final[list[Platform]] = [
    Platform.BINARY_SENSOR,
    Platform.CLIMATE,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.TIME,
    Platform.WATER_HEATER,
]

# Coordinator kinds. Every entity description names the coordinator it reads from.
COORDINATOR: Final = "coordinator"
ENERGY_COORDINATOR: Final = "energy_coordinator"
BUS_ERRORS_COORDINATOR: Final = "bus_errors_coordinator"

# Config entry data keys (CONF_USERNAME / CONF_PASSWORD / CONF_DEVICE come from HA).
API_URL_SETTING: Final = "api_url_setting"
API_USER_AGENT: Final = "api_user_agent"

# Options keys (CONF_SCAN_INTERVAL comes from HA).
ENERGY_SCAN_INTERVAL: Final = "energy_scan_interval"
BUS_ERRORS_SCAN_INTERVAL: Final = "bus_errors_scan_interval"

DEFAULT_SCAN_INTERVAL_SECONDS: Final = 180
DEFAULT_ENERGY_SCAN_INTERVAL_MINUTES: Final = 60
DEFAULT_BUS_ERRORS_SCAN_INTERVAL_SECONDS: Final = 600

# The Ariston cloud throttles aggressive polling; keep users out of trouble.
MIN_SCAN_INTERVAL_SECONDS: Final = 30
MIN_ENERGY_SCAN_INTERVAL_MINUTES: Final = 5
MIN_BUS_ERRORS_SCAN_INTERVAL_SECONDS: Final = 60

# Extra state attribute names.
ATTR_TARGET_TEMP_STEP: Final = "target_temp_step"
ATTR_HEAT_REQUEST: Final = "heat_request"
ATTR_ECONOMY_TEMP: Final = "economy_temp"
ATTR_HOLIDAY: Final = "holiday"
ATTR_ZONE: Final = "zone_number"
ATTR_ERRORS: Final = "errors"
