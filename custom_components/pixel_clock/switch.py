"""Switch entity: rotate through the apps automatically."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import PixelClockConfigEntry
from .entity import PixelClockEntity


async def async_setup_entry(hass: HomeAssistant, entry: PixelClockConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities([AutoRotateSwitch(entry.runtime_data, "auto_rotate")])


class AutoRotateSwitch(PixelClockEntity, SwitchEntity):
    @property
    def is_on(self) -> bool:
        return self.coordinator.settings.auto_rotate

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_settings(auto_rotate=True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_settings(auto_rotate=False)
