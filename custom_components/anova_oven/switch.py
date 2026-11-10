"""Support for Anova switches."""

from __future__ import annotations

import uuid

from homeassistant import config_entries
from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import AnovaCoordinator
from .entity import AnovaOvenDescriptionEntity
from .precision_oven import APOCommand

SWITCH_DESCRIPTIONS: list[SwitchEntityDescription] = [
    SwitchEntityDescription(
        key="lamp",
        translation_key="lamp",
        icon="mdi:lightbulb",
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
        AnovaOvenSwitch(device[0], coordinator, description)
        for device in coordinator.devices.items()
        for description in SWITCH_DESCRIPTIONS
    )


class AnovaOvenSwitch(AnovaOvenDescriptionEntity, SwitchEntity):
    """An Anova oven switch."""

    entity_description: SwitchEntityDescription

    @property
    def available(self) -> bool:
        """Return if the oven state is known."""
        if not super().available:
            return False
        device = self.coordinator.devices.get(self.cooker_id)
        return device is not None and device.state is not None

    @property
    def is_on(self) -> bool | None:
        """Return true if the lamp is on."""
        device = self.coordinator.devices.get(self.cooker_id)
        if device and device.state and device.state.sensor.nodes:
            return device.state.sensor.nodes.lamp_on
        return None

    async def _async_set_lamp(self, on: bool) -> None:
        """Send the lamp command to the oven."""
        await self.coordinator.api.send_command(
            APOCommand(
                command="CMD_APO_SET_LAMP",
                request_id=str(uuid.uuid4()),
                payload=APOCommand.Payload(
                    payload={"on": on},
                    type="CMD_APO_SET_LAMP",
                    id=self.cooker_id,
                ),
            )
        )

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the lamp on."""
        await self._async_set_lamp(True)

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the lamp off."""
        await self._async_set_lamp(False)
