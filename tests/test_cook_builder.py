"""Tests for the Anova cook command builders."""

import json

from custom_components.anova_oven.cook_builder import (
    CookParameters,
    build_custom_cook_payload,
    build_start_payload,
)
from custom_components.anova_oven.precision_oven import (
    OVEN_V1,
    OVEN_V2,
    APOCommand,
    APOStage,
)
from custom_components.anova_oven.util import dict_keys_to_camel_case, to_dict


def _parameters(**overrides):
    values = {
        "cooker_id": "01234",
        "target_temperature_celsius": 176.67,
        "target_temperature_fahrenheit": 350,
        "heating_top": True,
        "heating_rear": True,
    }
    values.update(overrides)
    return CookParameters(**values)


def test_v1_untimed_cook_is_single_stage():
    payload = build_start_payload(_parameters(), OVEN_V1)
    assert isinstance(payload, APOCommand.APOStartPayload)
    assert len(payload.stages) == 1
    assert payload.stages[0].type == "cook"
    assert payload.stages[0].timer is None
    assert payload.stages[0].temperature_bulbs.mode == "dry"


def test_v1_preheated_timer_adds_preheat_stage():
    payload = build_start_payload(
        _parameters(timer_seconds=1500, timer_mode="When Preheated"), OVEN_V1
    )
    assert [stage.type for stage in payload.stages] == ["preheat", "cook"]
    assert payload.stages[1].timer.initial == 1500
    assert payload.stages[0].temperature_bulbs.mode == "dry"


def test_v1_sous_vide_uses_wet_bulb_and_humidity():
    payload = build_start_payload(
        _parameters(
            sous_vide=True,
            target_temperature_celsius=60,
            target_temperature_fahrenheit=140,
            target_humidity=100,
        ),
        OVEN_V1,
    )
    stage = payload.stages[-1]
    assert stage.temperature_bulbs.mode == "wet"
    assert stage.steam_generators.mode == "relative-humidity"


def test_v2_payload_shape():
    payload = build_start_payload(_parameters(), OVEN_V2)
    assert isinstance(payload, APOCommand.APOStartPayloadV2)
    assert payload.type == "oven_v2"
    assert payload.cooker_id == "01234"
    assert payload.cookable_type == "manual"
    stage = payload.stages[0]
    assert stage.do.type == "cook"
    assert stage.exit == {"conditions": {"and": {}}}
    assert stage.entry is None
    serialized = dict_keys_to_camel_case(to_dict(payload))
    assert serialized["cookableType"] == "manual"
    assert serialized["stages"][0]["do"]["exhaustVent"] == {"state": "closed"}
    assert serialized["stages"][0]["do"]["temperatureBulbs"]["dry"]["setpoint"] == {
        "celsius": 176.67
    }


def test_v2_timer_conditions():
    payload = build_start_payload(
        _parameters(timer_seconds=600, timer_mode="When Preheated"), OVEN_V2
    )
    stage = payload.stages[0]
    assert stage.do.timer.initial == 600
    assert stage.do.timer.entry == {
        "conditions": {
            "and": {"nodes.temperatureBulbs.dry.current.celsius": {">=": 176.67}}
        }
    }
    assert stage.exit == {
        "conditions": {"and": {"nodes.timer.mode": {"=": "completed"}}}
    }


def test_v2_food_detected_condition():
    payload = build_start_payload(
        _parameters(timer_seconds=600, timer_mode="When Food Detected"), OVEN_V2
    )
    entry = payload.stages[0].do.timer.entry["conditions"]["and"]
    assert entry["nodes.cavityCamera.isEmpty"] == {"=": False}
    assert entry["userAction"] == {"=": True}


def test_custom_cook_v1_parses_stage():
    config = json.dumps(
        [
            {
                "id": "android-1",
                "type": "cook",
                "title": "",
                "temperature_bulbs": {"mode": "dry"},
                "heating_elements": {
                    "top": {"on": True},
                    "bottom": {"on": False},
                    "rear": {"on": False},
                },
                "fan": {"speed": 100},
                "vent": {"open": False},
            }
        ]
    )
    payload = build_custom_cook_payload("01234", OVEN_V1, config)
    assert isinstance(payload.stages[0], APOStage)
    assert payload.stages[0].type == "cook"


def test_custom_cook_v2_passes_raw_stages():
    stages = [
        {
            "id": "android-1",
            "do": {"type": "cook", "fan": {"speed": 100}},
            "entry": None,
            "exit": {"conditions": {"and": {}}},
        }
    ]
    payload = build_custom_cook_payload("01234", OVEN_V2, json.dumps(stages))
    assert payload.stages == stages
    assert payload.type == "oven_v2"


def test_v1_fan_speed_is_passed_through():
    payload = build_start_payload(_parameters(fan_speed=55), OVEN_V1)
    assert payload.stages[-1].fan.speed == 55


def test_v2_fan_speed_maps_to_enum():
    cases = {
        0: "off",
        20: "min",
        33: "min",
        34: "mid",
        66: "mid",
        67: "max",
        100: "max",
    }
    for percent, expected in cases.items():
        payload = build_start_payload(_parameters(fan_speed=percent), OVEN_V2)
        assert payload.stages[0].do.fan.speed == expected


def test_v2_fan_speed_serializes_as_enum():
    payload = build_start_payload(_parameters(fan_speed=100), OVEN_V2)
    serialized = dict_keys_to_camel_case(to_dict(payload))
    assert serialized["stages"][0]["do"]["fan"] == {"speed": "max"}
