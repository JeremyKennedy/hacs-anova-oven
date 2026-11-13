"""Config flow for Anova Precision Oven integration."""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import (
    CONF_ACCESS_TOKEN,
    CONF_DEVICES,
    CONF_TEMPERATURE_UNIT,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import AnovaOvenApi
from .const import (
    AUTH_METHOD_APP,
    AUTH_METHOD_PAT,
    CONF_APP_KEY,
    CONF_AUTH_METHOD,
    CONF_REFRESH_TOKEN,
    DOMAIN,
    AnovaUnitOfTemperature,
)
from .exceptions import InvalidAuth, NoDevicesFound
from .precision_oven import AnovaPrecisionOven

_LOGGER = logging.getLogger(__name__)

TEMPERATURE_UNIT_FIELD = vol.Required(
    CONF_TEMPERATURE_UNIT, default=AnovaUnitOfTemperature.CELSIUS
)

STEP_APP_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_APP_KEY): str,
        vol.Required(CONF_ACCESS_TOKEN): str,
        vol.Required(CONF_REFRESH_TOKEN): str,
        TEMPERATURE_UNIT_FIELD: vol.All(
            vol.Coerce(str), vol.In([e.value for e in AnovaUnitOfTemperature])
        ),
    }
)

STEP_PAT_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ACCESS_TOKEN): str,
        TEMPERATURE_UNIT_FIELD: vol.All(
            vol.Coerce(str), vol.In([e.value for e in AnovaUnitOfTemperature])
        ),
    }
)

STEP_OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Optional(
            CONF_TEMPERATURE_UNIT, default=AnovaUnitOfTemperature.CELSIUS
        ): vol.All(vol.Coerce(str), vol.In([e.value for e in AnovaUnitOfTemperature])),
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> list:
    """Validate the credentials and return the discovered devices."""
    auth_method = data.get(CONF_AUTH_METHOD, AUTH_METHOD_APP)
    api = AnovaOvenApi(
        session=async_get_clientsession(hass),
        app_key=data.get(CONF_APP_KEY, ""),
        access_token=data[CONF_ACCESS_TOKEN],
        refresh_token=data.get(CONF_REFRESH_TOKEN, ""),
        auth_method=auth_method,
    )

    devices_task = asyncio.create_task(api.get_devices())
    run_task = asyncio.create_task(api.run())
    try:
        done, _ = await asyncio.wait(
            {devices_task, run_task}, return_when=asyncio.FIRST_COMPLETED
        )
        if run_task in done and run_task.exception() is not None:
            raise run_task.exception()
        devices = await devices_task
    finally:
        await api.stop()
        for task in (devices_task, run_task):
            if not task.done():
                task.cancel()
        with suppress(asyncio.CancelledError):
            await run_task
    return devices


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Anova Precision Oven."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Let the user choose how to authenticate."""
        return self.async_show_menu(
            step_id="user",
            menu_options=[AUTH_METHOD_APP, AUTH_METHOD_PAT],
        )

    async def _async_discover(
        self, data: dict[str, Any], step_id: str, schema: vol.Schema
    ) -> FlowResult:
        """Validate the form, or show it again with an error."""
        errors: dict[str, str] = {}
        try:
            devices = await validate_input(self.hass, data)
        except InvalidAuth:
            errors["base"] = "invalid_auth"
        except NoDevicesFound:
            errors["base"] = "no_devices_found"
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown"
        else:
            auth_method = data[CONF_AUTH_METHOD]
            entry_data = {
                CONF_AUTH_METHOD: auth_method,
                CONF_ACCESS_TOKEN: data[CONF_ACCESS_TOKEN],
                CONF_DEVICES: serialize_device_list(devices),
            }
            if auth_method == AUTH_METHOD_APP:
                entry_data[CONF_APP_KEY] = data[CONF_APP_KEY]
                entry_data[CONF_REFRESH_TOKEN] = data[CONF_REFRESH_TOKEN]
            return self.async_create_entry(
                title="Anova Oven",
                data=entry_data,
                options={
                    CONF_TEMPERATURE_UNIT: data[CONF_TEMPERATURE_UNIT],
                },
            )

        return self.async_show_form(step_id=step_id, data_schema=schema, errors=errors)

    async def async_step_app(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Authenticate with the Anova app credentials (full command set)."""
        if user_input is not None:
            return await self._async_discover(
                {**user_input, CONF_AUTH_METHOD: AUTH_METHOD_APP},
                step_id="app",
                schema=STEP_APP_DATA_SCHEMA,
            )
        return self.async_show_form(step_id="app", data_schema=STEP_APP_DATA_SCHEMA)

    async def async_step_pat(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Authenticate with a personal access token (start/stop only)."""
        if user_input is not None:
            return await self._async_discover(
                {**user_input, CONF_AUTH_METHOD: AUTH_METHOD_PAT},
                step_id="pat",
                schema=STEP_PAT_DATA_SCHEMA,
            )
        return self.async_show_form(step_id="pat", data_schema=STEP_PAT_DATA_SCHEMA)

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return AnovaOvenOptionsFlowHandler(config_entry)


class AnovaOvenOptionsFlowHandler(config_entries.OptionsFlowWithConfigEntry):
    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            entry = self.async_create_entry(title="", data=user_input)
            return entry

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                STEP_OPTIONS_SCHEMA, self.config_entry.options
            ),
        )


def serialize_device_list(devices: list[AnovaPrecisionOven]) -> list[tuple[str, str]]:
    """Turn the device list into a serializable list that can be reconstructed."""
    return [(device.cooker_id, device.type) for device in devices]
