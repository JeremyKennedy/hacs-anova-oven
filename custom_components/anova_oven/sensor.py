"""Support for Anova Sensors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from homeassistant import config_entries
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    CONF_TEMPERATURE_UNIT,
    PERCENTAGE,
    UnitOfPower,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from .const import DOMAIN, AnovaUnitOfTemperature
from .coordinator import AnovaCoordinator
from .entity import AnovaOvenDescriptionEntity
from .precision_oven import OVEN_V1, OVEN_V2, APOState


@dataclass(frozen=True)
class AnovaOvenSensorEntityDescriptionMixin:
    """Describes the mixin variables for anova sensors."""

    value_fn: Callable[[APOState], float | int | str]
    extra_state_attributes: dict[str, Callable[[APOState], float | int | str]] = field(
        default_factory=dict
    )


@dataclass(frozen=True)
class AnovaOvenSensorEntityDescription(
    SensorEntityDescription, AnovaOvenSensorEntityDescriptionMixin
):
    """Describes a Anova sensor."""


V2_ONLY_KEYS = {
    "top_usage_hours",
    "rear_usage_hours",
    "bottom_usage_hours",
    "evaporator_usage_hours",
    "boiler_usage_hours",
}


def description_supported(
    description: AnovaOvenSensorEntityDescription, oven_type: str
) -> bool:
    """Return whether a description applies to the oven generation."""
    if description.device_class == SensorDeviceClass.ENUM:
        return oven_type == OVEN_V2
    if description.device_class == SensorDeviceClass.POWER_FACTOR:
        return oven_type == OVEN_V1
    if description.key in V2_ONLY_KEYS:
        return oven_type == OVEN_V2
    return True


def sensor_descriptions(
    unit_of_temperature: AnovaUnitOfTemperature,
) -> list[AnovaOvenSensorEntityDescription]:  # noqa: D103
    def temp_getter(x):
        match unit_of_temperature:
            case AnovaUnitOfTemperature.FAHRENHEIT:
                return x.fahrenheit
            case _:
                return x.celsius

    def probe_temperature(data: APOState):
        probe = data.sensor.nodes.temperature_probe
        return temp_getter(probe.temperature) if probe and probe.temperature else None

    def probe_target(data: APOState):
        probe = data.sensor.nodes.temperature_probe
        return (
            temp_getter(probe.target_temperature)
            if probe and probe.target_temperature
            else None
        )

    def usage_hours(element):
        return getattr(element, "usage_hours", 0)

    return [
        AnovaOvenSensorEntityDescription(
            key="mode",
            translation_key="mode",
            value_fn=lambda data: data.sensor.mode,
            extra_state_attributes={"raw_stages": lambda s: s.raw_stages},
        ),
        AnovaOvenSensorEntityDescription(
            key="temperature",
            translation_key="temperature",
            native_unit_of_measurement=unit_of_temperature,
            device_class=SensorDeviceClass.TEMPERATURE,
            state_class=SensorStateClass.MEASUREMENT,
            value_fn=lambda data: temp_getter(
                data.sensor.nodes.temperature_bulbs.temperature
            )
            if data.sensor.nodes.temperature_bulbs.temperature
            else None,
            extra_state_attributes={},
        ),
        AnovaOvenSensorEntityDescription(
            key="target_temperature",
            translation_key="target_temperature",
            native_unit_of_measurement=unit_of_temperature,
            device_class=SensorDeviceClass.TEMPERATURE,
            state_class=SensorStateClass.MEASUREMENT,
            value_fn=lambda data: temp_getter(
                data.sensor.nodes.temperature_bulbs.target_temperature
            )
            if data.sensor.nodes.temperature_bulbs.target_temperature
            else None,
            extra_state_attributes={},
        ),
        AnovaOvenSensorEntityDescription(
            key="temperature_probe",
            translation_key="temperature_probe",
            native_unit_of_measurement=unit_of_temperature,
            device_class=SensorDeviceClass.TEMPERATURE,
            state_class=SensorStateClass.MEASUREMENT,
            value_fn=probe_temperature,
            extra_state_attributes={},
        ),
        AnovaOvenSensorEntityDescription(
            key="target_temperature_probe",
            translation_key="target_temperature_probe",
            native_unit_of_measurement=unit_of_temperature,
            device_class=SensorDeviceClass.TEMPERATURE,
            state_class=SensorStateClass.MEASUREMENT,
            value_fn=probe_target,
            extra_state_attributes={},
        ),
        AnovaOvenSensorEntityDescription(
            key="rear_watts",
            device_class=SensorDeviceClass.POWER,
            native_unit_of_measurement=UnitOfPower.WATT,
            state_class=SensorStateClass.MEASUREMENT,
            translation_key="rear_watts",
            value_fn=lambda data: data.sensor.nodes.rear_heating.watts,
            extra_state_attributes={},
        ),
        AnovaOvenSensorEntityDescription(
            key="bottom_watts",
            device_class=SensorDeviceClass.POWER,
            native_unit_of_measurement=UnitOfPower.WATT,
            state_class=SensorStateClass.MEASUREMENT,
            translation_key="bottom_watts",
            value_fn=lambda data: data.sensor.nodes.bottom_heating.watts,
            extra_state_attributes={},
        ),
        AnovaOvenSensorEntityDescription(
            key="top_watts",
            device_class=SensorDeviceClass.POWER,
            native_unit_of_measurement=UnitOfPower.WATT,
            state_class=SensorStateClass.MEASUREMENT,
            translation_key="top_watts",
            value_fn=lambda data: data.sensor.nodes.top_heating.watts,
            extra_state_attributes={},
        ),
        AnovaOvenSensorEntityDescription(
            key="evaporator_watts",
            device_class=SensorDeviceClass.POWER,
            native_unit_of_measurement=UnitOfPower.WATT,
            state_class=SensorStateClass.MEASUREMENT,
            translation_key="evaporator_watts",
            value_fn=lambda data: data.sensor.nodes.evaporator.watts
            if data.sensor.nodes.evaporator
            else None,
            extra_state_attributes={},
        ),
        AnovaOvenSensorEntityDescription(
            key="boiler_watts",
            device_class=SensorDeviceClass.POWER,
            native_unit_of_measurement=UnitOfPower.WATT,
            state_class=SensorStateClass.MEASUREMENT,
            translation_key="boiler_watts",
            value_fn=lambda data: data.sensor.nodes.boiler.watts
            if data.sensor.nodes.boiler
            else None,
            extra_state_attributes={},
        ),
        AnovaOvenSensorEntityDescription(
            key="top_usage_hours",
            state_class=SensorStateClass.TOTAL_INCREASING,
            native_unit_of_measurement=UnitOfTime.HOURS,
            icon="mdi:clock-outline",
            translation_key="top_usage_hours",
            device_class=SensorDeviceClass.DURATION,
            value_fn=lambda data: usage_hours(data.sensor.nodes.top_heating),
            extra_state_attributes={},
        ),
        AnovaOvenSensorEntityDescription(
            key="rear_usage_hours",
            state_class=SensorStateClass.TOTAL_INCREASING,
            native_unit_of_measurement=UnitOfTime.HOURS,
            icon="mdi:clock-outline",
            translation_key="rear_usage_hours",
            device_class=SensorDeviceClass.DURATION,
            value_fn=lambda data: usage_hours(data.sensor.nodes.rear_heating),
            extra_state_attributes={},
        ),
        AnovaOvenSensorEntityDescription(
            key="bottom_usage_hours",
            state_class=SensorStateClass.TOTAL_INCREASING,
            native_unit_of_measurement=UnitOfTime.HOURS,
            icon="mdi:clock-outline",
            translation_key="bottom_usage_hours",
            device_class=SensorDeviceClass.DURATION,
            value_fn=lambda data: usage_hours(data.sensor.nodes.bottom_heating),
            extra_state_attributes={},
        ),
        AnovaOvenSensorEntityDescription(
            key="evaporator_usage_hours",
            state_class=SensorStateClass.TOTAL_INCREASING,
            native_unit_of_measurement=UnitOfTime.HOURS,
            icon="mdi:clock-outline",
            translation_key="evaporator_usage_hours",
            device_class=SensorDeviceClass.DURATION,
            value_fn=lambda data: usage_hours(data.sensor.nodes.evaporator)
            if data.sensor.nodes.evaporator
            else None,
            extra_state_attributes={},
        ),
        AnovaOvenSensorEntityDescription(
            key="boiler_usage_hours",
            state_class=SensorStateClass.TOTAL_INCREASING,
            native_unit_of_measurement=UnitOfTime.HOURS,
            icon="mdi:clock-outline",
            translation_key="boiler_usage_hours",
            device_class=SensorDeviceClass.DURATION,
            value_fn=lambda data: usage_hours(data.sensor.nodes.boiler)
            if data.sensor.nodes.boiler
            else None,
            extra_state_attributes={},
        ),
        AnovaOvenSensorEntityDescription(
            key="fan_speed",
            device_class=SensorDeviceClass.POWER_FACTOR,
            native_unit_of_measurement=PERCENTAGE,
            state_class=SensorStateClass.MEASUREMENT,
            translation_key="fan_speed",
            value_fn=lambda data: data.sensor.nodes.fan_speed,
            extra_state_attributes={},
        ),
        AnovaOvenSensorEntityDescription(
            key="fan_speed",
            device_class=SensorDeviceClass.ENUM,
            options=["off", "min", "mid", "max"],
            translation_key="fan_speed",
            value_fn=lambda data: data.sensor.nodes.fan_speed,
            extra_state_attributes={},
        ),
        AnovaOvenSensorEntityDescription(
            key="steam_generator_mode",
            translation_key="steam_generator_mode",
            value_fn=lambda data: data.sensor.nodes.steam_generator.mode,
            extra_state_attributes={},
        ),
        AnovaOvenSensorEntityDescription(
            key="relative_humidity",
            device_class=SensorDeviceClass.HUMIDITY,
            native_unit_of_measurement=PERCENTAGE,
            state_class=SensorStateClass.MEASUREMENT,
            translation_key="relative_humidity",
            value_fn=lambda data: data.sensor.nodes.steam_generator.relative_humidity,
            extra_state_attributes={},
        ),
        AnovaOvenSensorEntityDescription(
            key="target_humidity",
            device_class=SensorDeviceClass.HUMIDITY,
            native_unit_of_measurement=PERCENTAGE,
            state_class=SensorStateClass.MEASUREMENT,
            translation_key="target_humidity",
            value_fn=lambda data: data.sensor.nodes.steam_generator.target_humidity,
            extra_state_attributes={},
        ),
        AnovaOvenSensorEntityDescription(
            key="cook_time",
            state_class=SensorStateClass.TOTAL_INCREASING,
            native_unit_of_measurement=UnitOfTime.SECONDS,
            icon="mdi:clock-outline",
            translation_key="cook_time",
            device_class=SensorDeviceClass.DURATION,
            value_fn=lambda data: data.sensor.nodes.cook.seconds_elapsed,
            extra_state_attributes={},
        ),
        AnovaOvenSensorEntityDescription(
            key="timer",
            state_class=SensorStateClass.TOTAL_INCREASING,
            native_unit_of_measurement=UnitOfTime.SECONDS,
            icon="mdi:clock-outline",
            translation_key="timer",
            device_class=SensorDeviceClass.DURATION,
            value_fn=lambda data: data.sensor.nodes.timer.current
            if data.sensor.nodes.timer
            else None,
            extra_state_attributes={},
        ),
        AnovaOvenSensorEntityDescription(
            key="timer_initial",
            state_class=SensorStateClass.TOTAL,
            native_unit_of_measurement=UnitOfTime.SECONDS,
            icon="mdi:clock-outline",
            translation_key="timer_initial",
            device_class=SensorDeviceClass.DURATION,
            value_fn=lambda data: data.sensor.nodes.timer.initial
            if data.sensor.nodes.timer
            else None,
            extra_state_attributes={},
        ),
        AnovaOvenSensorEntityDescription(
            key="timer_mode",
            translation_key="timer_mode",
            value_fn=lambda data: data.sensor.nodes.timer.mode
            if data.sensor.nodes.timer
            else None,
            extra_state_attributes={},
        ),
        AnovaOvenSensorEntityDescription(
            key="active_stage",
            state_class=SensorStateClass.MEASUREMENT,
            translation_key="active_stage",
            value_fn=lambda data: data.stages.active,
            extra_state_attributes={},
        ),
        AnovaOvenSensorEntityDescription(
            key="stages_count",
            state_class=SensorStateClass.MEASUREMENT,
            translation_key="stages_count",
            value_fn=lambda data: data.stages.count,
            extra_state_attributes={},
        ),
    ]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: config_entries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Anova device."""
    coordinator: AnovaCoordinator = hass.data[DOMAIN][entry.entry_id]
    unit_of_temperature = AnovaUnitOfTemperature(
        entry.options.get(CONF_TEMPERATURE_UNIT, AnovaUnitOfTemperature.CELSIUS)
    )
    async_add_entities(
        AnovaOvenSensor(device[0], coordinator, description)
        for device in coordinator.devices.items()
        for description in sensor_descriptions(unit_of_temperature)
        if description_supported(description, device[1].type or OVEN_V1)
    )


class AnovaOvenSensor(AnovaOvenDescriptionEntity, SensorEntity):
    """A sensor using Anova coordinator."""

    entity_description: AnovaOvenSensorEntityDescription

    @property
    def native_value(self) -> StateType:
        """Return the state."""
        if state := self.coordinator.devices[self.cooker_id].state:
            if hasattr(self.entity_description, "extra_state_attributes"):
                for k, getter in self.entity_description.extra_state_attributes.items():
                    self._attr_extra_state_attributes[k] = getter(state)
            return self.entity_description.value_fn(state)
        return None
