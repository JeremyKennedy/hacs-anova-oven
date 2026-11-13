"""Smoke tests for integration setup and entity registration."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant.const import (
    CONF_ACCESS_TOKEN,
    CONF_DEVICES,
    CONF_TEMPERATURE_UNIT,
)
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.anova_oven.const import (
    CONF_APP_KEY,
    CONF_REFRESH_TOKEN,
    DOMAIN,
    AnovaUnitOfTemperature,
)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading the custom integration."""
    yield


def _config_entry(cooker_id: str, oven_type: str) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="Anova Oven",
        data={
            CONF_APP_KEY: "app-key",
            CONF_ACCESS_TOKEN: "access-token",
            CONF_REFRESH_TOKEN: "refresh-token",
            CONF_DEVICES: [(cooker_id, oven_type)],
        },
        options={
            CONF_TEMPERATURE_UNIT: AnovaUnitOfTemperature.FAHRENHEIT.value,
        },
        entry_id=f"test-{oven_type}",
    )


def _fake_api() -> MagicMock:
    api = MagicMock()
    api.run = AsyncMock()
    api.stop = AsyncMock()
    api.unit_of_temperature = AnovaUnitOfTemperature.FAHRENHEIT
    return api


async def _setup(hass, entry):
    entry.add_to_hass(hass)
    with (
        patch("custom_components.anova_oven.AnovaOvenApi", return_value=_fake_api()),
        patch(
            "custom_components.anova_oven.coordinator.sleep",
            new=AsyncMock(),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()


async def test_v1_entities_register(hass):
    entry = _config_entry("01234v1", "oven_v1")
    await _setup(hass, entry)

    entities = hass.states.async_entity_ids()
    assert "sensor.anova_precision_oven_temperature" in entities
    assert "sensor.anova_precision_oven_fan_speed" in entities
    assert "sensor.anova_precision_oven_boiler_watts" in entities
    assert "sensor.anova_precision_oven_evaporator_watts" in entities
    assert "binary_sensor.anova_precision_oven_exhaust_vent_open" in entities
    assert "switch.anova_precision_oven_lamp" in entities

    assert "sensor.anova_precision_oven_rear_usage_hours" not in entities
    assert "sensor.anova_precision_oven_boiler_usage_hours" not in entities
    assert "binary_sensor.anova_precision_oven_waste_water_tank_full" not in entities

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert (
        hass.states.get("sensor.anova_precision_oven_temperature").state
        == "unavailable"
    )
    assert DOMAIN not in hass.data or entry.entry_id not in hass.data[DOMAIN]


async def test_v2_entities_register(hass):
    entry = _config_entry("01234v2", "oven_v2")
    await _setup(hass, entry)

    entities = hass.states.async_entity_ids()
    assert "sensor.anova_precision_oven_temperature" in entities
    assert "sensor.anova_precision_oven_fan_speed" in entities
    assert "sensor.anova_precision_oven_rear_usage_hours" in entities
    assert "sensor.anova_precision_oven_boiler_usage_hours" in entities
    assert "binary_sensor.anova_precision_oven_exhaust_vent_open" in entities
    assert "binary_sensor.anova_precision_oven_waste_water_tank_full" in entities
    assert "switch.anova_precision_oven_lamp" in entities

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert (
        hass.states.get("sensor.anova_precision_oven_temperature").state
        == "unavailable"
    )
    assert DOMAIN not in hass.data or entry.entry_id not in hass.data[DOMAIN]
