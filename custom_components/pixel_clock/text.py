"""Text entity: type a message, it is shown as a notification."""

from __future__ import annotations

from homeassistant.components.text import TextEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import Notification, PixelClockConfigEntry
from .entity import PixelClockEntity


async def async_setup_entry(hass: HomeAssistant, entry: PixelClockConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities([MessageText(entry.runtime_data, "message")])


class MessageText(PixelClockEntity, TextEntity):
    _attr_native_max = 255
    _attr_native_value = ""

    async def async_set_value(self, value: str) -> None:
        self._attr_native_value = value
        if value.strip():
            self.coordinator.notify(Notification(text=value))
        self.async_write_ha_state()
