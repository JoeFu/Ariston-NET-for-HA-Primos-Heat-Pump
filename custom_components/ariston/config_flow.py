"""Config flow for the Ariston integration."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from ariston import Ariston, DeviceAttribute
from ariston.ariston_api import ConnectionException
from ariston.const import ARISTON_API_URL, ARISTON_USER_AGENT

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_DEVICE, CONF_PASSWORD, CONF_SCAN_INTERVAL, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    API_URL_SETTING,
    API_USER_AGENT,
    BUS_ERRORS_SCAN_INTERVAL,
    DEFAULT_BUS_ERRORS_SCAN_INTERVAL_SECONDS,
    DEFAULT_ENERGY_SCAN_INTERVAL_MINUTES,
    DEFAULT_SCAN_INTERVAL_SECONDS,
    DOMAIN,
    ENERGY_SCAN_INTERVAL,
    MIN_BUS_ERRORS_SCAN_INTERVAL_SECONDS,
    MIN_ENERGY_SCAN_INTERVAL_MINUTES,
    MIN_SCAN_INTERVAL_SECONDS,
)
from .coordinator import is_auth_error

_LOGGER = logging.getLogger(__name__)

CONF_SELECT_DEVICE = "select_device"


def _credentials_schema(defaults: Mapping[str, Any], advanced: bool) -> vol.Schema:
    """Username/password form; API url and user agent only in advanced mode."""
    schema: dict[Any, Any] = {
        vol.Required(CONF_USERNAME, default=defaults.get(CONF_USERNAME, vol.UNDEFINED)): (
            TextSelector(TextSelectorConfig(type=TextSelectorType.EMAIL, autocomplete="username"))
        ),
        vol.Required(CONF_PASSWORD): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD, autocomplete="current-password")
        ),
    }
    if advanced:
        schema[
            vol.Optional(API_URL_SETTING, default=defaults.get(API_URL_SETTING, ARISTON_API_URL))
        ] = TextSelector(TextSelectorConfig(type=TextSelectorType.URL))
        schema[
            vol.Optional(API_USER_AGENT, default=defaults.get(API_USER_AGENT, ARISTON_USER_AGENT))
        ] = TextSelector()
    return vol.Schema(schema)


def _interval_selector(minimum: int, unit: str) -> vol.All:
    """Build a number box with a lower bound and a unit, coerced to int."""
    return vol.All(
        NumberSelector(
            NumberSelectorConfig(
                min=minimum, step=1, mode=NumberSelectorMode.BOX, unit_of_measurement=unit
            )
        ),
        vol.Coerce(int),
    )


class AristonConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the Ariston config flow."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._credentials: dict[str, Any] = {}
        self._devices: dict[str, dict[str, Any]] = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> AristonOptionsFlow:
        """Return the options flow handler."""
        return AristonOptionsFlow()

    async def _async_connect(
        self, user_input: Mapping[str, Any]
    ) -> tuple[Ariston | None, str | None]:
        """Try to log in. Return (client, None) or (None, error_key)."""
        ariston = Ariston()
        try:
            connected = await ariston.async_connect(
                user_input[CONF_USERNAME],
                user_input[CONF_PASSWORD],
                user_input.get(API_URL_SETTING, ARISTON_API_URL),
                user_input.get(API_USER_AGENT, ARISTON_USER_AGENT),
            )
        except ConnectionException as err:
            return None, "invalid_auth" if is_auth_error(err) else "cannot_connect"
        except Exception:
            _LOGGER.exception("Unexpected error while connecting to Ariston")
            return None, "unknown"
        if not connected:
            return None, "invalid_auth"
        return ariston, None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for the Ariston NET account and discover its devices."""
        errors: dict[str, str] = {}
        if user_input is not None:
            ariston, error = await self._async_connect(user_input)
            if ariston is None:
                errors["base"] = error or "unknown"
            else:
                self._credentials = {
                    CONF_USERNAME: user_input[CONF_USERNAME],
                    CONF_PASSWORD: user_input[CONF_PASSWORD],
                    API_URL_SETTING: user_input.get(API_URL_SETTING, ARISTON_API_URL),
                    API_USER_AGENT: user_input.get(API_USER_AGENT, ARISTON_USER_AGENT),
                }
                try:
                    cloud_devices = await ariston.async_discover()
                except ConnectionException:
                    errors["base"] = "cannot_connect"
                else:
                    configured = self._async_current_ids(include_ignore=False)
                    self._devices = {
                        device[DeviceAttribute.GW]: device
                        for device in cloud_devices
                        if device.get(DeviceAttribute.GW)
                        and device[DeviceAttribute.GW] not in configured
                    }
                    if not cloud_devices:
                        return self.async_abort(reason="no_devices_found")
                    if not self._devices:
                        return self.async_abort(reason="already_configured")
                    if len(self._devices) == 1:
                        return await self._async_create_entry(next(iter(self._devices.values())))
                    return await self.async_step_select()

        return self.async_show_form(
            step_id="user",
            data_schema=_credentials_schema(user_input or {}, self.show_advanced_options),
            errors=errors,
        )

    async def async_step_select(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Let the user pick one of several devices on the account."""
        if user_input is not None:
            return await self._async_create_entry(self._devices[user_input[CONF_SELECT_DEVICE]])

        options = [
            SelectOptionDict(
                value=gateway,
                label=f"{device.get(DeviceAttribute.NAME) or gateway} ({device.get(DeviceAttribute.SN, '?')})",
            )
            for gateway, device in self._devices.items()
        ]
        return self.async_show_form(
            step_id="select",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SELECT_DEVICE): SelectSelector(
                        SelectSelectorConfig(options=options, mode=SelectSelectorMode.DROPDOWN)
                    )
                }
            ),
        )

    async def _async_create_entry(self, cloud_device: dict[str, Any]) -> ConfigFlowResult:
        """Create the config entry for the chosen device."""
        await self.async_set_unique_id(cloud_device[DeviceAttribute.GW])
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=cloud_device.get(DeviceAttribute.NAME) or cloud_device[DeviceAttribute.GW],
            data={**self._credentials, CONF_DEVICE: cloud_device},
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """Start re-authentication after the cloud rejected our credentials."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the (new) password and reload the entry."""
        reauth_entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            candidate = {**reauth_entry.data, **user_input}
            ariston, error = await self._async_connect(candidate)
            if ariston is None:
                errors["base"] = error or "unknown"
            else:
                return self.async_update_reload_and_abort(
                    reauth_entry,
                    data_updates={
                        CONF_USERNAME: user_input[CONF_USERNAME],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                        API_URL_SETTING: user_input.get(
                            API_URL_SETTING, reauth_entry.data.get(API_URL_SETTING, ARISTON_API_URL)
                        ),
                        API_USER_AGENT: user_input.get(
                            API_USER_AGENT,
                            reauth_entry.data.get(API_USER_AGENT, ARISTON_USER_AGENT),
                        ),
                    },
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=_credentials_schema(reauth_entry.data, self.show_advanced_options),
            description_placeholders={"device": reauth_entry.title},
            errors=errors,
        )


class AristonOptionsFlow(OptionsFlow):
    """Let the user tune how often the cloud is polled."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show and save the polling intervals."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        options = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_SECONDS),
                    ): _interval_selector(MIN_SCAN_INTERVAL_SECONDS, "s"),
                    vol.Required(
                        ENERGY_SCAN_INTERVAL,
                        default=options.get(
                            ENERGY_SCAN_INTERVAL, DEFAULT_ENERGY_SCAN_INTERVAL_MINUTES
                        ),
                    ): _interval_selector(MIN_ENERGY_SCAN_INTERVAL_MINUTES, "min"),
                    vol.Required(
                        BUS_ERRORS_SCAN_INTERVAL,
                        default=options.get(
                            BUS_ERRORS_SCAN_INTERVAL, DEFAULT_BUS_ERRORS_SCAN_INTERVAL_SECONDS
                        ),
                    ): _interval_selector(MIN_BUS_ERRORS_SCAN_INTERVAL_SECONDS, "s"),
                }
            ),
            last_step=True,
        )
