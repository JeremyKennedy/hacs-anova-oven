"""Parse Anova oven state events into the integration data model.

The V1 and V2 ovens report different payload shapes. The discriminator is the
``type`` field on the event payload (``oven_v1`` / ``oven_v2``).
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from .precision_oven import (
    OVEN_V1,
    OVEN_V2,
    AnovaPrecisionOven,
    APOSensor,
    APOState,
    Temperature,
)

STEAM_MODES = {
    "relative-humidity": "relativeHumidity",
    "steam-percentage": "steamPercentage",
}


@dataclass
class ParsedState:
    cooker_id: str
    oven_type: str
    state: APOState
    raw_data: dict


def _celsius_to_fahrenheit(celsius: float) -> float:
    return celsius * 9 / 5 + 32


def _temperature(value: dict | None) -> Temperature | None:
    if not value or "celsius" not in value:
        return None
    celsius = value["celsius"]
    if "fahrenheit" in value:
        return Temperature(celsius=celsius, fahrenheit=value["fahrenheit"])
    return Temperature(
        celsius=celsius,
        fahrenheit=_celsius_to_fahrenheit(celsius),
    )


def _stages(cook: dict) -> tuple[int | None, int]:
    stages = cook.get("stages") or []
    active = None
    for index, stage in enumerate(stages, start=1):
        if stage.get("id") == cook.get("activeStageId"):
            active = index
            break
    return active, len(stages)


def _steam_values(steam_generators: dict) -> tuple[int | None, int | None]:
    mode = steam_generators.get("mode")
    key = STEAM_MODES.get(mode) or ("relativeHumidity" if mode == "idle" else "")
    values = steam_generators.get(key, {}) or {}
    return values.get("current"), values.get("setpoint")


def parse_event_state(payload: dict) -> ParsedState:
    """Parse an ``EVENT_APO_STATE`` payload for either oven generation."""
    state = payload.get("state") or {}
    oven_type = payload.get("type") or state.get("type") or OVEN_V1
    if oven_type == OVEN_V2:
        return _parse_v2(payload)
    return _parse_v1(payload)


def _parse_v1(payload: dict) -> ParsedState:
    state = payload["state"]
    nodes = state["nodes"]
    bulbs = nodes.get("temperatureBulbs", {})
    heating = nodes.get("heatingElements", {})
    steam_generators = nodes.get("steamGenerators", {})
    cook = state.get("cook", {})
    timer = nodes.get("timer", {})
    probe = nodes.get("temperatureProbe")
    humidity, target_humidity = _steam_values(steam_generators)
    active_stage, stage_count = _stages(cook)
    bulb = bulbs.get(bulbs.get("mode"), {})

    parsed = APOState(
        sensor=APOSensor(
            mode=(state.get("state") or {}).get("mode", "idle"),
            firmware_version=(state.get("systemInfo") or {}).get(
                "firmwareVersion", "unknown"
            ),
            nodes=APOSensor.Nodes(
                cook=APOSensor.Nodes.Cook(
                    seconds_elapsed=cook.get("secondsElapsed", 0)
                ),
                temperature_probe=APOSensor.Nodes.TemperatureProbe(
                    temperature=_temperature(probe.get("current")),
                    target_temperature=_temperature(probe.get("setpoint")),
                )
                if probe
                else None,
                temperature_bulbs=APOSensor.Nodes.TemperatureBulbs(
                    mode=bulbs.get("mode", "dry"),
                    temperature=_temperature(bulb.get("current")),
                    target_temperature=_temperature(bulb.get("setpoint")),
                    dosed=(bulbs.get("wet") or {}).get("dosed", False),
                    dose_failed=(bulbs.get("wet") or {}).get("doseFailed", False),
                ),
                rear_heating=_heating_element(heating.get("rear", {})),
                bottom_heating=_heating_element(heating.get("bottom", {})),
                top_heating=_heating_element(heating.get("top", {})),
                steam_generator=APOSensor.Nodes.SteamGenerator(
                    mode=steam_generators.get("mode", "idle"),
                    relative_humidity=humidity,
                    target_humidity=target_humidity,
                ),
                evaporator=APOSensor.Nodes.SteamGeneratorType(
                    watts=(steam_generators.get("evaporator") or {}).get("watts", 0),
                ),
                boiler=APOSensor.Nodes.SteamGeneratorType(
                    watts=(steam_generators.get("boiler") or {}).get("watts", 0),
                ),
                timer=APOSensor.Nodes.Timer(
                    mode=timer.get("mode", "idle"),
                    initial=timer.get("initial", 0),
                    current=timer.get("current", 0),
                ),
                lamp_on=(nodes.get("lamp") or {}).get("on", False),
                door_closed=(nodes.get("door") or {}).get("closed", True),
                water_tank_empty=(nodes.get("waterTank") or {}).get("empty", False),
                fan_speed=(nodes.get("fan") or {}).get("speed", 0),
                vent_open=(nodes.get("vent") or {}).get("open"),
            ),
        ),
        stages=APOState.Stages(active=active_stage, count=stage_count),
        raw_stages=json.dumps(cook.get("stages", [])),
    )
    return ParsedState(
        cooker_id=payload["cookerId"],
        oven_type=OVEN_V1,
        state=parsed,
        raw_data=payload,
    )


def _heating_element(data: dict) -> APOSensor.Nodes.HeatingElement:
    return APOSensor.Nodes.HeatingElement(
        watts=data.get("watts", 0),
        on=data.get("on", False),
        usage_hours=data.get("usageHours", 0),
    )


def _parse_v2(payload: dict) -> ParsedState:
    state = payload["state"]
    nodes = state["nodes"]
    bulbs = nodes.get("temperatureBulbs", {})
    heating = nodes.get("heatingElements", {})
    steam_generators = nodes.get("steamGenerators", {})
    cook = state.get("cook", {})
    timer = nodes.get("timer", {})
    probe = nodes.get("temperatureProbe")
    humidity, target_humidity = _steam_values(steam_generators)
    active_stage, stage_count = _stages(cook)
    bulb = bulbs.get(bulbs.get("mode"), {})

    parsed = APOState(
        sensor=APOSensor(
            mode=(state.get("state") or {}).get("mode", "idle"),
            firmware_version=(state.get("systemInfo") or {}).get(
                "firmwareVersion", "unknown"
            ),
            nodes=APOSensor.Nodes(
                cook=APOSensor.Nodes.Cook(
                    seconds_elapsed=cook.get("secondsElapsed", 0)
                ),
                temperature_probe=APOSensor.Nodes.TemperatureProbe(
                    temperature=_temperature(probe.get("current")),
                    target_temperature=_temperature(probe.get("setpoint")),
                )
                if probe
                else None,
                temperature_bulbs=APOSensor.Nodes.TemperatureBulbs(
                    mode=bulbs.get("mode", "dry"),
                    temperature=_temperature(bulb.get("current")),
                    target_temperature=_temperature(bulb.get("setpoint")),
                    dosed=(bulbs.get("wet") or {}).get("dosed", False),
                    dose_failed=(bulbs.get("wet") or {}).get("doseFailed", False),
                ),
                rear_heating=_heating_element(heating.get("rear", {})),
                bottom_heating=_heating_element(heating.get("bottom", {})),
                top_heating=_heating_element(heating.get("top", {})),
                steam_generator=APOSensor.Nodes.SteamGenerator(
                    mode=steam_generators.get("mode", "idle"),
                    relative_humidity=humidity,
                    target_humidity=target_humidity,
                ),
                evaporator=APOSensor.Nodes.SteamGeneratorType(
                    watts=(steam_generators.get("evaporator") or {}).get("watts", 0),
                    usage_hours=(steam_generators.get("evaporator") or {}).get(
                        "usageHours", 0
                    ),
                ),
                boiler=APOSensor.Nodes.SteamGeneratorType(
                    watts=(steam_generators.get("boiler") or {}).get("watts", 0),
                    usage_hours=(steam_generators.get("boiler") or {}).get(
                        "usageHours", 0
                    ),
                ),
                timer=APOSensor.Nodes.Timer(
                    mode=timer.get("mode", "idle"),
                    initial=timer.get("initial", 0),
                    current=timer.get("current", 0),
                ),
                lamp_on=(nodes.get("doorLamp") or {}).get("on", False),
                door_closed=(nodes.get("door") or {}).get("closed", True),
                water_tank_empty=(nodes.get("waterTank") or {}).get("empty", False),
                fan_speed=(nodes.get("fan") or {}).get("speed", "off"),
                vent_open=(nodes["exhaustVent"]["state"] == "open")
                if nodes.get("exhaustVent")
                else None,
                waste_water_full=(nodes.get("wasteWaterTank") or {}).get("full"),
            ),
        ),
        stages=APOState.Stages(active=active_stage, count=stage_count),
        raw_stages=json.dumps(cook.get("stages", [])),
    )
    return ParsedState(
        cooker_id=payload["cookerId"],
        oven_type=OVEN_V2,
        state=parsed,
        raw_data=payload,
    )


def apply_state(device: AnovaPrecisionOven, parsed: ParsedState) -> None:
    """Attach a parsed state to a device."""
    device.state = parsed.state
    device.raw_data = parsed.raw_data
