"""Tests for the Anova oven state parser."""

from custom_components.anova_oven.precision_oven import OVEN_V1, OVEN_V2
from custom_components.anova_oven.state_parser import parse_event_state

V1_PAYLOAD = {
    "command": "EVENT_APO_STATE",
    "payload": {
        "cookerId": "01234V1",
        "state": {
            "nodes": {
                "door": {"closed": True},
                "fan": {"failed": False, "speed": 42},
                "heatingElements": {
                    "bottom": {"failed": False, "on": True, "watts": 0},
                    "rear": {"failed": False, "on": False, "watts": 0},
                    "top": {"failed": False, "on": False, "watts": 0},
                },
                "lamp": {"failed": False, "on": True, "preference": "on"},
                "steamGenerators": {
                    "boiler": {"celsius": 38.75, "watts": 0},
                    "evaporator": {"celsius": 38.75, "watts": 0},
                    "mode": "idle",
                    "relativeHumidity": {"current": 55},
                },
                "temperatureBulbs": {
                    "dry": {
                        "current": {"celsius": 24.36, "fahrenheit": 75.85},
                        "setpoint": {"celsius": 58.33, "fahrenheit": 137},
                    },
                    "dryBottom": {"current": {"celsius": 23.73, "fahrenheit": 74.72}},
                    "dryTop": {"current": {"celsius": 24.36, "fahrenheit": 75.85}},
                    "mode": "dry",
                    "wet": {
                        "current": {"celsius": 24.36, "fahrenheit": 75.85},
                        "doseFailed": False,
                        "dosed": False,
                    },
                },
                "temperatureProbe": {"connected": False},
                "timer": {"current": 0, "initial": 0, "mode": "idle"},
                "vent": {"open": True},
                "waterTank": {"empty": False},
            },
            "state": {"mode": "idle"},
            "systemInfo": {"firmwareVersion": "2.1.7"},
            "cook": {"secondsElapsed": 0, "stages": []},
        },
        "type": "oven_v1",
    },
}

V2_PAYLOAD = {
    "command": "EVENT_APO_STATE",
    "payload": {
        "cookerId": "01234V2",
        "type": "oven_v2",
        "state": {
            "state": {"mode": "idle"},
            "nodes": {
                "temperatureBulbs": {
                    "dryBottom": {"current": {"celsius": 17.31}},
                    "dryTop": {"current": {"celsius": 16.97}},
                    "dry": {
                        "setpoint": {"celsius": 25},
                        "current": {"celsius": 17.19},
                    },
                    "wet": {"current": {"celsius": 17.38}, "dosed": False},
                    "mode": "dry",
                },
                "waterTank": {"removed": False, "empty": True, "low": False},
                "steamGenerators": {
                    "boiler": {"usageHours": 0.8, "watts": 0, "celsius": 21.63},
                    "mode": "idle",
                    "evaporator": {"usageHours": 0.4, "watts": 0, "celsius": 15.36},
                },
                "heatingElements": {
                    "top": {"watts": 0, "on": False, "usageHours": 1.2},
                    "rear": {"watts": 0, "usageHours": 38.1, "on": True},
                    "bottom": {"watts": 0, "on": False, "usageHours": 1.2},
                },
                "exhaustFan": {"speed": "off"},
                "exhaustVent": {"state": "closed"},
                "wasteWaterTank": {"full": False, "removed": False},
                "doorLamp": {"preferences": "on", "on": False},
                "timer": {"mode": "idle"},
                "fan": {"failed": False, "speed": "max"},
                "temperatureProbe": {
                    "current": {"celsius": 0},
                    "connected": False,
                },
                "door": {"closed": True},
            },
            "systemInfo": {"firmwareVersion": "11_167_1.0.34_01.00.05"},
            "cook": {"secondsElapsed": 0, "stages": []},
        },
    },
}


def test_parse_v1_state():
    parsed = parse_event_state(V1_PAYLOAD["payload"])
    assert parsed.oven_type == OVEN_V1
    nodes = parsed.state.sensor.nodes
    assert parsed.state.sensor.mode == "idle"
    assert nodes.lamp_on is True
    assert nodes.fan_speed == 42
    assert nodes.water_tank_empty is False
    assert nodes.temperature_bulbs.temperature.celsius == 24.36
    assert nodes.temperature_bulbs.target_temperature.fahrenheit == 137
    assert nodes.steam_generator.relative_humidity == 55
    assert nodes.evaporator.watts == 0
    assert nodes.vent_open is True


def test_parse_v2_state():
    parsed = parse_event_state(V2_PAYLOAD["payload"])
    assert parsed.oven_type == OVEN_V2
    nodes = parsed.state.sensor.nodes
    assert nodes.lamp_on is False
    assert nodes.fan_speed == "max"
    assert nodes.water_tank_empty is True
    assert nodes.temperature_bulbs.temperature.celsius == 17.19
    assert nodes.rear_heating.usage_hours == 38.1
    assert nodes.evaporator.usage_hours == 0.4
    assert nodes.temperature_probe.temperature.celsius == 0
    assert nodes.vent_open is False
    assert nodes.waste_water_full is False
    # V2 only reports celsius; fahrenheit is derived.
    assert nodes.temperature_bulbs.temperature.fahrenheit == 62.942


def test_parse_v1_missing_setpoint_is_tolerated():
    payload = {
        "payload": {
            "cookerId": "01234V1",
            "type": "oven_v1",
            "state": {
                "nodes": {
                    "temperatureBulbs": {
                        "mode": "wet",
                        "wet": {"current": {"celsius": 24.36}},
                    },
                },
                "state": {"mode": "cook"},
                "systemInfo": {"firmwareVersion": "2.1.7"},
            },
        }
    }
    parsed = parse_event_state(payload["payload"])
    assert parsed.state.sensor.nodes.temperature_bulbs.target_temperature is None
