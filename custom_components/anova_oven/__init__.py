"""The Anova Precision Oven integration."""

from __future__ import annotations

import uuid

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_DEVICE_ID,
    CONF_ACCESS_TOKEN,
    CONF_DEVICES,
    CONF_TEMPERATURE_UNIT,
    Platform,
)
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import (
    aiohttp_client,
    config_validation as cv,
    device_registry,
)
from homeassistant.helpers.typing import ConfigType

from .api import AnovaOvenApi
from .const import (
    AUTH_METHOD_APP,
    CONF_APP_KEY,
    CONF_AUTH_METHOD,
    CONF_REFRESH_TOKEN,
    DOMAIN,
    AnovaUnitOfTemperature,
)
from .coordinator import AnovaCoordinator
from .cook_builder import (
    CookParameters,
    build_custom_cook_payload,
    build_start_payload,
)
from .precision_oven import OVEN_V1, AnovaPrecisionOven, APOCommand
from .util import to_celsius, to_fahrenheit

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Anova Precision Oven from a config entry."""
    entry.async_on_unload(entry.add_update_listener(update_listener))

    data = entry.data | entry.options

    hass.data.setdefault(DOMAIN, {})
    devices = [
        AnovaPrecisionOven(
            cooker_id=device[0],
            type=device[1],
        )
        for device in data[CONF_DEVICES]
    ]
    api = AnovaOvenApi(
        session=aiohttp_client.async_get_clientsession(hass),
        app_key=data.get(CONF_APP_KEY, ""),
        access_token=data[CONF_ACCESS_TOKEN],
        refresh_token=data.get(CONF_REFRESH_TOKEN, ""),
        existing_devices=devices,
        unit_of_temperature=data.get(
            CONF_TEMPERATURE_UNIT, AnovaUnitOfTemperature.CELSIUS
        ),
        auth_method=data.get(CONF_AUTH_METHOD, AUTH_METHOD_APP),
    )
    coordinator = AnovaCoordinator(api=api, hass=hass, entry=entry, devices=devices)
    await coordinator.async_setup()
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    coordinator: AnovaCoordinator | None = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if coordinator:
        await coordinator.async_unload()

    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up  component."""
    # hass.data[DOMAIN] = {}

    def _oven_type(api: AnovaOvenApi, cook_id: str) -> str:
        device = api.devices.get(cook_id)
        return getattr(device, "type", None) or OVEN_V1

    def get_api(device_id) -> tuple[str, AnovaOvenApi]:
        cook_id = None
        api: AnovaOvenApi | None = None
        dr = device_registry.async_get(hass)
        if device := dr.async_get(device_id):
            for ce_key in device.config_entries:
                if ce := hass.data[DOMAIN].get(ce_key):
                    api: AnovaOvenApi = ce.api
                    for k, v in device.identifiers:
                        if k == DOMAIN:
                            cook_id = v
                            break
        if not api or not device_id:
            raise ConfigEntryNotReady("Device is not found or doesn't ready.")
        return cook_id, api

    async def start_cook(call: ServiceCall):
        cook_id, api = get_api(call.data[ATTR_DEVICE_ID])
        timer = call.data.get("timer")
        probe = call.data.get("temperature_probe")
        unit_of_temperature = api.unit_of_temperature
        if timer and probe:
            raise ValueError("Only probe or timer can be setup at one.")

        sous_vide = bool(call.data.get("sous_vide") or False)

        target_temperature_celsius = None
        target_temperature_fahrenheit = None
        temperature_probe_celsius = None
        temperature_probe_fahrenheit = None

        match unit_of_temperature:
            case AnovaUnitOfTemperature.CELSIUS:
                if (
                    target_temperature_celsius := call.data.get(
                        "target_temperature_celsius"
                    )
                ) is None:
                    raise ValueError(
                        "This service requires field Target temperature, please enter a valid value."
                    )
                target_temperature_fahrenheit = to_fahrenheit(
                    target_temperature_celsius
                )
                if temperature_probe_celsius := call.data.get(
                    "temperature_probe_celsius"
                ):
                    temperature_probe_fahrenheit = to_fahrenheit(
                        temperature_probe_celsius
                    )
                if sous_vide and target_temperature_celsius > 100:
                    raise ValueError(
                        "Target temperature could not exceed 100°C in sous vide mode."
                    )
            case AnovaUnitOfTemperature.FAHRENHEIT:
                if (
                    target_temperature_fahrenheit := call.data.get(
                        "target_temperature_fahrenheit"
                    )
                ) is None:
                    raise ValueError(
                        "This service requires field Target temperature, please enter a valid value."
                    )
                target_temperature_celsius = to_celsius(target_temperature_fahrenheit)
                if temperature_probe_fahrenheit := call.data.get(
                    "temperature_probe_fahrenheit"
                ):
                    temperature_probe_celsius = to_celsius(temperature_probe_fahrenheit)
                if sous_vide and target_temperature_fahrenheit > 212:
                    raise ValueError(
                        "Target temperature could not exceed 212°F in sous vide mode."
                    )

        timer_seconds = None
        if timer:
            timer_seconds = (
                timer["hours"] * 3600 + timer["minutes"] * 60 + timer["seconds"]
            )

        fan_speed = call.data.get("fan_speed")
        fan_speed = 100 if fan_speed is None else int(fan_speed)
        if not 0 <= fan_speed <= 100:
            raise ValueError("Fan speed must be between 0 and 100 percent.")

        parameters = CookParameters(
            cooker_id=cook_id,
            target_temperature_celsius=target_temperature_celsius,
            target_temperature_fahrenheit=target_temperature_fahrenheit,
            sous_vide=sous_vide,
            heating_top=bool(call.data.get("heating_top", False)),
            heating_bottom=bool(call.data.get("heating_bottom", False)),
            heating_rear=bool(call.data.get("heating_rear", True)),
            target_humidity=call.data.get("target_humidity"),
            temperature_probe_celsius=temperature_probe_celsius,
            temperature_probe_fahrenheit=temperature_probe_fahrenheit,
            timer_seconds=timer_seconds,
            timer_mode=call.data.get("timer_mode"),
            title=call.data.get("title") or "",
            fan_speed=fan_speed,
        )
        await api.send_command(
            APOCommand(
                command="CMD_APO_START",
                request_id=str(uuid.uuid4()),
                payload=APOCommand.Payload(
                    payload=build_start_payload(parameters, _oven_type(api, cook_id)),
                    type="CMD_APO_START",
                    id=cook_id,
                ),
            )
        )

    async def start_custom_cook(call: ServiceCall):
        cook_id, api = get_api(call.data[ATTR_DEVICE_ID])
        config = call.data.get("config")
        await api.send_command(
            APOCommand(
                command="CMD_APO_START",
                request_id=str(uuid.uuid4()),
                payload=APOCommand.Payload(
                    payload=build_custom_cook_payload(
                        cook_id,
                        _oven_type(api, cook_id),
                        config,
                        call.data.get("title") or "",
                    ),
                    type="CMD_APO_START",
                    id=cook_id,
                ),
            )
        )

    async def stop_cook(call: ServiceCall):
        api: AnovaOvenApi
        cook_id, api = get_api(call.data[ATTR_DEVICE_ID])
        await api.send_command(
            APOCommand(
                command="CMD_APO_STOP",
                request_id=str(uuid.uuid4()),
                payload=APOCommand.Payload(
                    type="CMD_APO_STOP", id=cook_id, payload=None
                ),
            )
        )

    hass.services.async_register(
        DOMAIN,
        "start_cook",
        start_cook,
    )

    hass.services.async_register(
        DOMAIN,
        "start_custom_cook",
        start_custom_cook,
    )

    hass.services.async_register(
        DOMAIN,
        "stop_cook",
        stop_cook,
    )

    return True


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)
