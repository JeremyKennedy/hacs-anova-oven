"""Support for Anova binary sensors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant import config_entries
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import AnovaCoordinator
from .entity import AnovaOvenDescriptionEntity
from .precision_oven import OVEN_V1, OVEN_V2, APOState


@dataclass(frozen=True)
class AnovaOvenBinarySensorEntityDescriptionMixin:
    """Describes the mixin variables for anova binary sensors."""

    value_fn: Callable[[APOState], bool]


@dataclass(frozen=True)
class AnovaOvenBinarySensorEntityDescription(
    BinarySensorEntityDescription, AnovaOvenBinarySensorEntityDescriptionMixin
):
    """Describes an Anova binary sensor."""


SENSOR_DESCRIPTIONS: list[AnovaOvenBinarySensorEntityDescription] = [
    AnovaOvenBinarySensorEntityDescription(
        key="sous_vide",
        translation_key="sous_vide",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda data: data.sensor.nodes.temperature_bulbs.mode == "wet",
    ),
    AnovaOvenBinarySensorEntityDescription(
        key="lamp_on",
        translation_key="lamp_on",
        device_class=BinarySensorDeviceClass.LIGHT,
        value_fn=lambda data: data.sensor.nodes.lamp_on,
    ),
    AnovaOvenBinarySensorEntityDescription(
        key="door_closed",
        translation_key="door_closed",
        device_class=BinarySensorDeviceClass.DOOR,
        value_fn=lambda data: not data.sensor.nodes.door_closed,
    ),
    AnovaOvenBinarySensorEntityDescription(
        key="water_tank_empty",
        translation_key="water_tank_empty",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda data: data.sensor.nodes.water_tank_empty,
    ),
    AnovaOvenBinarySensorEntityDescription(
        key="exhaust_vent_open",
        translation_key="exhaust_vent_open",
        device_class=BinarySensorDeviceClass.OPENING,
        value_fn=lambda data: data.sensor.nodes.vent_open,
    ),
    AnovaOvenBinarySensorEntityDescription(
        key="waste_water_tank_full",
        translation_key="waste_water_tank_full",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda data: data.sensor.nodes.waste_water_full,
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: config_entries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Anova device."""
    coordinator: AnovaCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        AnovaOvenBinarySensor(device[0], coordinator, description)
        for device in coordinator.devices.items()
        for description in SENSOR_DESCRIPTIONS
        if description.key != "waste_water_tank_full"
        or (device[1].type or OVEN_V1) == OVEN_V2
    )


class AnovaOvenBinarySensor(AnovaOvenDescriptionEntity, BinarySensorEntity):
    """A binary sensor using the Anova coordinator."""

    entity_description: AnovaOvenBinarySensorEntityDescription

    @property
    def is_on(self) -> bool | None:
        """Return true when the sensor is on."""
        device = self.coordinator.devices.get(self.cooker_id)
        if device and device.state and device.state.sensor.nodes:
            return self.entity_description.value_fn(device.state)
        return None
