import logging
from dataclasses import dataclass
from typing import Any, Generic, Optional, TypeVar

_LOGGER = logging.getLogger(__name__)

P = TypeVar("P")

OVEN_V1 = "oven_v1"
OVEN_V2 = "oven_v2"


@dataclass
class Temperature:
    celsius: float
    fahrenheit: float


@dataclass
class APOSensor:
    @dataclass
    class Nodes:
        @dataclass
        class TemperatureBulbs:
            mode: str
            dosed: bool
            dose_failed: bool
            temperature: Temperature | None
            target_temperature: Temperature | None

        @dataclass
        class TemperatureProbe:
            temperature: Temperature | None
            target_temperature: Temperature | None

        @dataclass
        class HeatingElement:
            watts: int
            on: bool
            usage_hours: float = 0

        @dataclass
        class SteamGenerator:
            mode: str
            relative_humidity: int | None
            target_humidity: int | None

        @dataclass
        class SteamGeneratorType:
            watts: int = 0
            usage_hours: float = 0

        @dataclass
        class Cook:
            seconds_elapsed: int

        @dataclass
        class Timer:
            mode: str
            initial: int
            current: int

        cook: Cook
        timer: Timer | None
        temperature_bulbs: TemperatureBulbs
        temperature_probe: TemperatureProbe | None
        steam_generator: SteamGenerator
        rear_heating: HeatingElement
        bottom_heating: HeatingElement
        top_heating: HeatingElement

        lamp_on: bool
        door_closed: bool
        water_tank_empty: bool
        fan_speed: int | str
        evaporator: SteamGeneratorType | None = None
        boiler: SteamGeneratorType | None = None
        vent_open: bool | None = None
        waste_water_full: bool | None = None

    mode: str
    firmware_version: str
    nodes: Nodes | None = None


@dataclass
class APOState:
    @dataclass
    class Stages:
        active: int
        count: int

    sensor: APOSensor
    stages: Stages
    raw_stages: str


class Target:
    @property
    def reached(self) -> bool:
        pass


@dataclass
class ProbeTarget(Target):
    temperature: Temperature
    target_temperature: Temperature

    @property
    def reached(self) -> bool:
        return (
            self.temperature
            and self.target_temperature
            and self.temperature.celsius >= self.target_temperature.celsius
        )


@dataclass
class TimerTarget(Target):
    initial: int
    current: int

    @property
    def reached(self) -> bool:
        return self.current and self.initial and self.current >= self.initial


class AnovaPrecisionOven:
    raw_data: Any

    def __init__(self, cooker_id: str, type: str) -> None:
        self.cooker_id = cooker_id
        self.type = type
        self.state: APOState | None = None
        self.temperature_unit: str = "C"


@dataclass
class APOStage:
    """A first generation oven cook stage."""

    @dataclass
    class TemperatureSetpoint:
        fahrenheit: int
        celsius: int

    @dataclass
    class TemperatureBulb:
        setpoint: "APOStage.TemperatureSetpoint"

    @dataclass
    class TemperatureBulbs:
        mode: str
        dry: Optional["APOStage.TemperatureBulb"] = None
        wet: Optional["APOStage.TemperatureBulb"] = None

    @dataclass
    class On:
        on: bool

    @dataclass
    class HeatingElements:
        bottom: "APOStage.On"
        top: "APOStage.On"
        rear: "APOStage.On"

    @dataclass(frozen=True)
    class Fan:
        speed: int

    @dataclass(frozen=True)
    class Vent:
        open: bool

    @dataclass(frozen=True)
    class Timer:
        initial: int

    @dataclass(frozen=True)
    class Probe:
        setpoint: Optional["APOStage.TemperatureSetpoint"] = None

    @dataclass(frozen=True)
    class SteamGenerators:
        @dataclass(frozen=True)
        class Setpoint:
            setpoint: int

        mode: str
        relative_humidity: Setpoint
        steam_percentage: Setpoint

    id: str
    title: str
    type: str
    temperature_bulbs: TemperatureBulbs
    heating_elements: HeatingElements
    fan: Fan
    vent: Vent
    step_type: str = "stage"
    description: str = ""
    user_action_required: bool = False
    rack_position: int = 3
    steam_generators: SteamGenerators | None = None
    timer_added: bool = False
    timer: Timer | None = None
    probe_added: bool = False
    temperature_probe: Probe | None = None


@dataclass
class APOStageV2:
    """A second generation oven cook stage.

    V2 stages carry the actions in ``do`` and gate them with ``entry``/``exit``
    conditions instead of the flat preheat/cook stages used by the V1 oven.
    """

    @dataclass
    class TemperatureSetpoint:
        celsius: float

    @dataclass
    class TemperatureBulb:
        setpoint: "APOStageV2.TemperatureSetpoint"

    @dataclass
    class TemperatureBulbs:
        mode: str
        dry: Optional["APOStageV2.TemperatureBulb"] = None
        wet: Optional["APOStageV2.TemperatureBulb"] = None

    @dataclass
    class On:
        on: bool

    @dataclass
    class HeatingElements:
        bottom: "APOStageV2.On"
        top: "APOStageV2.On"
        rear: "APOStageV2.On"

    @dataclass(frozen=True)
    class Fan:
        speed: int | str

    @dataclass(frozen=True)
    class Vent:
        state: str

    @dataclass(frozen=True)
    class Timer:
        initial: int
        entry: dict | None = None

    @dataclass(frozen=True)
    class Probe:
        setpoint: Optional["APOStageV2.TemperatureSetpoint"] = None

    @dataclass(frozen=True)
    class SteamGenerators:
        @dataclass(frozen=True)
        class Setpoint:
            setpoint: int

        mode: str
        relative_humidity: Setpoint
        steam_percentage: Setpoint

    @dataclass(frozen=True)
    class Action:
        type: str
        fan: "APOStageV2.Fan"
        heating_elements: "APOStageV2.HeatingElements"
        exhaust_vent: "APOStageV2.Vent"
        temperature_bulbs: "APOStageV2.TemperatureBulbs"
        timer: Optional["APOStageV2.Timer"] = None
        steam_generators: Optional["APOStageV2.SteamGenerators"] = None
        temperature_probe: Optional["APOStageV2.Probe"] = None

    id: str
    do: Action
    title: str
    description: str = ""
    entry: dict | None = None
    exit: dict | None = None
    rack_position: int = 3


@dataclass
class APOCommand(Generic[P]):
    @dataclass
    class Payload(Generic[P]):
        payload: P | None
        type: str
        id: str

    @dataclass
    class APOStartPayload:
        cook_id: str
        stages: list[APOStage]

    @dataclass
    class APOStartPayloadV2:
        cook_id: str
        cooker_id: str
        type: str
        cookable_type: str
        origin_source: str
        title: str
        stages: list[APOStageV2]

    command: str
    request_id: str
    payload: Payload[P]
