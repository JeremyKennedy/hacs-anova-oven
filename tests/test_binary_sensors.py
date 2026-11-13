"""Tests for the Anova binary sensor entities."""

from unittest.mock import MagicMock

from homeassistant.components.binary_sensor import BinarySensorDeviceClass

from custom_components.anova_oven.binary_sensor import (
    SENSOR_DESCRIPTIONS,
    AnovaOvenBinarySensor,
)
from custom_components.anova_oven.precision_oven import OVEN_V1, AnovaPrecisionOven
from custom_components.anova_oven.state_parser import parse_event_state

from tests.test_state_parser import V1_PAYLOAD

COOKER_ID = "01234V1"


def _entity(key: str, coordinator) -> AnovaOvenBinarySensor:
    description = next(d for d in SENSOR_DESCRIPTIONS if d.key == key)
    return AnovaOvenBinarySensor(COOKER_ID, coordinator, description)


def _coordinator() -> MagicMock:
    parsed = parse_event_state(V1_PAYLOAD["payload"])
    device = AnovaPrecisionOven(cooker_id=COOKER_ID, type=OVEN_V1)
    device.state = parsed.state
    coordinator = MagicMock()
    coordinator.devices = {COOKER_ID: device}
    return coordinator


def test_lamp_sensor_is_a_binary_sensor():
    entity = _entity("lamp_on", _coordinator())
    assert entity.device_class == BinarySensorDeviceClass.LIGHT
    assert entity.is_on is True
    assert entity.state == "on"


def test_door_sensor_reports_open_when_door_is_open():
    coordinator = _coordinator()
    coordinator.devices[COOKER_ID].state.sensor.nodes.door_closed = False
    entity = _entity("door_closed", coordinator)
    assert entity.device_class == BinarySensorDeviceClass.DOOR
    assert entity.is_on is True
    assert entity.state == "on"


def test_door_sensor_reports_closed_when_door_is_closed():
    entity = _entity("door_closed", _coordinator())
    assert entity.is_on is False
    assert entity.state == "off"


def test_vent_sensor_uses_opening_device_class():
    entity = _entity("exhaust_vent_open", _coordinator())
    assert entity.device_class == BinarySensorDeviceClass.OPENING
    assert entity.is_on is True


def test_water_tank_sensor_reports_problem_when_empty():
    coordinator = _coordinator()
    coordinator.devices[COOKER_ID].state.sensor.nodes.water_tank_empty = True
    entity = _entity("water_tank_empty", coordinator)
    assert entity.device_class == BinarySensorDeviceClass.PROBLEM
    assert entity.is_on is True


def test_sensor_is_unavailable_without_state():
    coordinator = MagicMock()
    coordinator.devices = {
        COOKER_ID: AnovaPrecisionOven(cooker_id=COOKER_ID, type=OVEN_V1)
    }
    entity = _entity("lamp_on", coordinator)
    assert entity.is_on is None
