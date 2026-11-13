"""Tests for the config flow and auth method selection."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_ACCESS_TOKEN, CONF_TEMPERATURE_UNIT
from homeassistant.data_entry_flow import FlowResultType

from custom_components.anova_oven.const import (
    AUTH_METHOD_APP,
    AUTH_METHOD_PAT,
    CONF_APP_KEY,
    CONF_AUTH_METHOD,
    CONF_REFRESH_TOKEN,
    DOMAIN,
)
from custom_components.anova_oven.config_flow import validate_input
from custom_components.anova_oven.exceptions import NoDevicesFound
from custom_components.anova_oven.precision_oven import AnovaPrecisionOven


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading the custom integration."""
    yield


def _fake_api_class(record: dict):
    class FakeApi:
        def __init__(self, **kwargs):
            record.update(kwargs)

        async def run(self):
            return None

        async def get_devices(self):
            return [AnovaPrecisionOven(cooker_id="01234", type="oven_v1")]

        async def stop(self):
            return None

    return FakeApi


async def test_flow_offers_both_auth_methods(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] == FlowResultType.MENU
    assert result["step_id"] == "user"
    assert set(result["menu_options"]) == {AUTH_METHOD_APP, AUTH_METHOD_PAT}


async def test_pat_flow_creates_entry_without_app_credentials(hass):
    record: dict = {}
    with patch(
        "custom_components.anova_oven.config_flow.AnovaOvenApi",
        _fake_api_class(record),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"next_step_id": AUTH_METHOD_PAT}
        )
        assert result["step_id"] == "pat"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_ACCESS_TOKEN: "anova-token",
                CONF_TEMPERATURE_UNIT: "°C",
            },
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    entry = result["result"]
    assert entry.data[CONF_AUTH_METHOD] == AUTH_METHOD_PAT
    assert entry.data[CONF_ACCESS_TOKEN] == "anova-token"
    assert CONF_APP_KEY not in entry.data
    assert CONF_REFRESH_TOKEN not in entry.data
    assert record["auth_method"] == AUTH_METHOD_PAT
    assert record["app_key"] == ""


async def test_app_flow_keeps_full_credentials(hass):
    record: dict = {}
    with patch(
        "custom_components.anova_oven.config_flow.AnovaOvenApi",
        _fake_api_class(record),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"next_step_id": AUTH_METHOD_APP}
        )
        assert result["step_id"] == "app"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_APP_KEY: "app-key",
                CONF_ACCESS_TOKEN: "access-token",
                CONF_REFRESH_TOKEN: "refresh-token",
                CONF_TEMPERATURE_UNIT: "°C",
            },
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    entry = result["result"]
    assert entry.data[CONF_AUTH_METHOD] == AUTH_METHOD_APP
    assert entry.data[CONF_APP_KEY] == "app-key"
    assert entry.data[CONF_REFRESH_TOKEN] == "refresh-token"
    assert record["auth_method"] == AUTH_METHOD_APP


async def test_validate_input_pat_uses_token_only(hass):
    record: dict = {}
    api = MagicMock()
    api.run = AsyncMock()
    api.stop = AsyncMock()
    api.get_devices = AsyncMock(
        return_value=[AnovaPrecisionOven(cooker_id="01234", type="oven_v2")]
    )
    with patch(
        "custom_components.anova_oven.config_flow.AnovaOvenApi",
        return_value=api,
    ) as api_class:
        devices = await validate_input(
            hass,
            {
                CONF_AUTH_METHOD: AUTH_METHOD_PAT,
                CONF_ACCESS_TOKEN: "anova-token",
            },
        )
    record = api_class.call_args.kwargs
    assert devices[0].cooker_id == "01234"
    assert record["auth_method"] == AUTH_METHOD_PAT
    assert record["access_token"] == "anova-token"
    assert record["app_key"] == ""
    assert record["refresh_token"] == ""


async def test_validate_input_surfaces_auth_failure(hass):
    from custom_components.anova_oven.exceptions import InvalidAuth

    api = MagicMock()
    api.get_devices = AsyncMock(side_effect=NoDevicesFound)
    api.stop = AsyncMock()

    async def _run():
        raise InvalidAuth("rejected")

    api.run = _run

    with (
        patch(
            "custom_components.anova_oven.config_flow.AnovaOvenApi",
            return_value=api,
        ),
        pytest.raises(InvalidAuth),
    ):
        await validate_input(
            hass,
            {
                CONF_AUTH_METHOD: AUTH_METHOD_PAT,
                CONF_ACCESS_TOKEN: "anova-bad",
            },
        )
