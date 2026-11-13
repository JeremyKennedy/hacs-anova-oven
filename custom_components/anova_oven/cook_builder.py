"""Build Anova cook commands for both oven generations."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

from .const import PLATFORM
from .precision_oven import (
    OVEN_V2,
    APOCommand,
    APOStage,
    APOStageV2,
)
from .util import dict_keys_to_snake_case

TIMER_MODE_PREHEATED = "When Preheated"
TIMER_MODE_MANUAL = "Manually"
TIMER_MODE_FOOD_DETECTED = "When Food Detected"
TIMER_MODE_FOOD_REMOVED = "When Food Removed"


@dataclass
class CookParameters:
    cooker_id: str
    target_temperature_celsius: float
    target_temperature_fahrenheit: float
    sous_vide: bool = False
    heating_top: bool = False
    heating_bottom: bool = False
    heating_rear: bool = True
    target_humidity: int | None = None
    temperature_probe_celsius: float | None = None
    temperature_probe_fahrenheit: float | None = None
    timer_seconds: int | None = None
    timer_mode: str | None = None
    title: str = ""
    fan_speed: int = 100


def _cook_id() -> str:
    return f"{PLATFORM}-{uuid.uuid4()}"


def _v2_fan_speed(speed: int) -> str:
    """Map a 0-100 fan percentage to the V2 fan enum."""
    if speed <= 0:
        return "off"
    if speed <= 33:
        return "min"
    if speed <= 66:
        return "mid"
    return "max"


def build_v1_stages(parameters: CookParameters) -> list[APOStage]:
    """Build the flat preheat/cook stages understood by V1 ovens."""
    preheat_required = parameters.timer_mode in (
        TIMER_MODE_PREHEATED,
        TIMER_MODE_MANUAL,
    )
    user_action_required = parameters.timer_mode == TIMER_MODE_MANUAL

    preheat_stage = APOStage(
        step_type="stage",
        id=_cook_id(),
        title=parameters.title,
        description="",
        type="preheat",
        user_action_required=user_action_required,
        temperature_bulbs=APOStage.TemperatureBulbs(
            dry=APOStage.TemperatureBulb(
                setpoint=APOStage.TemperatureSetpoint(
                    celsius=parameters.target_temperature_celsius,
                    fahrenheit=parameters.target_temperature_fahrenheit,
                )
            )
            if not parameters.sous_vide
            else None,
            wet=APOStage.TemperatureBulb(
                setpoint=APOStage.TemperatureSetpoint(
                    celsius=parameters.target_temperature_celsius,
                    fahrenheit=parameters.target_temperature_fahrenheit,
                )
            )
            if parameters.sous_vide
            else None,
            mode="wet" if parameters.sous_vide else "dry",
        ),
        heating_elements=APOStage.HeatingElements(
            bottom=APOStage.On(on=parameters.heating_bottom),
            top=APOStage.On(on=parameters.heating_top),
            rear=APOStage.On(on=parameters.heating_rear),
        ),
        fan=APOStage.Fan(speed=parameters.fan_speed),
        vent=APOStage.Vent(open=False),
        rack_position=3,
        steam_generators=APOStage.SteamGenerators(
            mode="relative-humidity" if parameters.sous_vide else "steam-percentage",
            relative_humidity=APOStage.SteamGenerators.Setpoint(
                setpoint=parameters.target_humidity
                if parameters.target_humidity is not None
                else (100 if parameters.sous_vide else 0)
            )
            if parameters.sous_vide
            else None,
            steam_percentage=APOStage.SteamGenerators.Setpoint(
                setpoint=parameters.target_humidity or 0
            )
            if not parameters.sous_vide
            else None,
        )
        if parameters.target_humidity or parameters.sous_vide
        else None,
        probe_added=parameters.temperature_probe_celsius is not None,
        temperature_probe=APOStage.Probe(
            setpoint=APOStage.TemperatureSetpoint(
                celsius=parameters.temperature_probe_celsius,
                fahrenheit=parameters.temperature_probe_fahrenheit,
            )
        )
        if parameters.temperature_probe_celsius is not None
        else None,
    )
    cook_stage = APOStage(
        step_type="stage",
        id=_cook_id(),
        title=parameters.title,
        description="",
        type="cook",
        user_action_required=user_action_required,
        temperature_bulbs=preheat_stage.temperature_bulbs,
        heating_elements=preheat_stage.heating_elements,
        fan=preheat_stage.fan,
        vent=preheat_stage.vent,
        rack_position=preheat_stage.rack_position,
        steam_generators=preheat_stage.steam_generators,
        timer_added=parameters.timer_seconds is not None,
        timer=APOStage.Timer(initial=parameters.timer_seconds)
        if parameters.timer_seconds is not None
        else None,
        probe_added=preheat_stage.probe_added,
        temperature_probe=preheat_stage.temperature_probe,
    )

    stages = []
    if preheat_required:
        stages.append(preheat_stage)
    stages.append(cook_stage)
    return stages


def _timer_entry_conditions(parameters: CookParameters) -> dict:
    """Build the V2 entry condition that starts the timer."""
    mode = "wet" if parameters.sous_vide else "dry"
    match parameters.timer_mode:
        case "When Preheated":
            conditions = {
                f"nodes.temperatureBulbs.{mode}.current.celsius": {
                    ">=": parameters.target_temperature_celsius
                }
            }
        case "Manually":
            conditions = {"userAction": {"=": True}}
        case "When Food Detected":
            conditions = {
                "nodes.cavityCamera.isEmpty": {"=": False},
                "userAction": {"=": True},
            }
        case "When Food Removed":
            conditions = {
                "nodes.cavityCamera.isEmpty": {"=": True},
                "userAction": {"=": True},
            }
        case _:
            conditions = {}
    return {"and": conditions}


def build_v2_stages(parameters: CookParameters) -> list[APOStageV2]:
    """Build the single conditional stage understood by V2 ovens."""
    timer = None
    exit_conditions: dict = {"conditions": {"and": {}}}
    if parameters.timer_seconds is not None:
        timer = APOStageV2.Timer(
            initial=parameters.timer_seconds,
            entry={"conditions": _timer_entry_conditions(parameters)},
        )
        exit_conditions = {
            "conditions": {"and": {"nodes.timer.mode": {"=": "completed"}}}
        }

    action = APOStageV2.Action(
        type="cook",
        fan=APOStageV2.Fan(speed=_v2_fan_speed(parameters.fan_speed)),
        heating_elements=APOStageV2.HeatingElements(
            bottom=APOStageV2.On(on=parameters.heating_bottom),
            top=APOStageV2.On(on=parameters.heating_top),
            rear=APOStageV2.On(on=parameters.heating_rear),
        ),
        exhaust_vent=APOStageV2.Vent(state="closed"),
        temperature_bulbs=APOStageV2.TemperatureBulbs(
            mode="wet" if parameters.sous_vide else "dry",
            dry=APOStageV2.TemperatureBulb(
                setpoint=APOStageV2.TemperatureSetpoint(
                    celsius=parameters.target_temperature_celsius
                )
            )
            if not parameters.sous_vide
            else None,
            wet=APOStageV2.TemperatureBulb(
                setpoint=APOStageV2.TemperatureSetpoint(
                    celsius=parameters.target_temperature_celsius
                )
            )
            if parameters.sous_vide
            else None,
        ),
        timer=timer,
        steam_generators=APOStageV2.SteamGenerators(
            mode="relative-humidity" if parameters.sous_vide else "steam-percentage",
            relative_humidity=APOStageV2.SteamGenerators.Setpoint(
                setpoint=parameters.target_humidity
                if parameters.target_humidity is not None
                else (100 if parameters.sous_vide else 0)
            )
            if parameters.sous_vide
            else None,
            steam_percentage=APOStageV2.SteamGenerators.Setpoint(
                setpoint=parameters.target_humidity or 0
            )
            if not parameters.sous_vide
            else None,
        )
        if parameters.target_humidity or parameters.sous_vide
        else None,
        temperature_probe=APOStageV2.Probe(
            setpoint=APOStageV2.TemperatureSetpoint(
                celsius=parameters.temperature_probe_celsius
            )
        )
        if parameters.temperature_probe_celsius is not None
        else None,
    )

    return [
        APOStageV2(
            id=_cook_id(),
            do=action,
            title=parameters.title,
            description="",
            entry=None,
            exit=exit_conditions,
        )
    ]


def build_start_payload(
    parameters: CookParameters, oven_type: str
) -> APOCommand.APOStartPayload | APOCommand.APOStartPayloadV2:
    """Build the ``CMD_APO_START`` payload for the oven generation."""
    if oven_type == OVEN_V2:
        return APOCommand.APOStartPayloadV2(
            cook_id=_cook_id(),
            cooker_id=parameters.cooker_id,
            type=OVEN_V2,
            cookable_type="manual",
            origin_source=PLATFORM,
            title=parameters.title,
            stages=build_v2_stages(parameters),
        )
    return APOCommand.APOStartPayload(
        cook_id=_cook_id(),
        stages=build_v1_stages(parameters),
    )


def build_custom_cook_payload(
    cooker_id: str, oven_type: str, config: str, title: str = ""
) -> APOCommand.APOStartPayload | APOCommand.APOStartPayloadV2:
    """Build a start payload from a raw stage array."""
    raw_stages = json.loads(config)
    if oven_type == OVEN_V2:
        return APOCommand.APOStartPayloadV2(
            cook_id=_cook_id(),
            cooker_id=cooker_id,
            type=OVEN_V2,
            cookable_type="manual",
            origin_source=PLATFORM,
            title=title,
            stages=raw_stages,
        )
    return APOCommand.APOStartPayload(
        cook_id=_cook_id(),
        stages=[APOStage(**dict_keys_to_snake_case(stage)) for stage in raw_stages],
    )
