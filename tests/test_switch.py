"""Tests for the Anova lamp switch."""

from contextlib import suppress
from unittest.mock import AsyncMock, MagicMock

from custom_components.anova_oven.precision_oven import OVEN_V1, AnovaPrecisionOven
from custom_components.anova_oven.state_parser import parse_event_state
from custom_components.anova_oven.switch import SWITCH_DESCRIPTIONS, AnovaOvenSwitch

from tests.test_state_parser import V1_PAYLOAD

COOKER_ID = "01234V1"


def _setup(lamp_on: bool):
    parsed = parse_event_state(V1_PAYLOAD["payload"])
    device = AnovaPrecisionOven(cooker_id=COOKER_ID, type=OVEN_V1)
    device.state = parsed.state
    device.state.sensor.nodes.lamp_on = lamp_on

    coordinator = MagicMock()
    coordinator.devices = {COOKER_ID: device}
    coordinator.api.send_command = AsyncMock()
    entity = AnovaOvenSwitch(COOKER_ID, coordinator, SWITCH_DESCRIPTIONS[0])
    return entity, device, coordinator


async def test_turn_off_updates_the_lamp_state():
    entity, device, coordinator = _setup(lamp_on=True)

    await entity.async_turn_off()

    assert device.state.sensor.nodes.lamp_on is False
    assert entity.is_on is False
    coordinator.api.send_command.assert_awaited_once()
    coordinator.async_set_updated_data.assert_called_once_with(device.state)


async def test_turn_on_updates_the_lamp_state():
    entity, device, coordinator = _setup(lamp_on=False)

    await entity.async_turn_on()

    assert device.state.sensor.nodes.lamp_on is True
    assert entity.is_on is True
    coordinator.async_set_updated_data.assert_called_once_with(device.state)


async def test_failed_command_does_not_update_the_lamp_state():
    entity, device, coordinator = _setup(lamp_on=True)
    coordinator.api.send_command.side_effect = RuntimeError("boom")

    with suppress(RuntimeError):
        await entity.async_turn_off()

    assert device.state.sensor.nodes.lamp_on is True
    coordinator.async_set_updated_data.assert_not_called()
