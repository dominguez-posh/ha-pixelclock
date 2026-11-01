"""Light entity: panel power and brightness."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import ATTR_BRIGHTNESS, ColorMode, LightEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import PixelClockConfigEntry
from .entity import PixelClockEntity


async def async_setup_entry(hass: HomeAssistant, entry: PixelClockConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities([PixelClockLight(entry.runtime_data, "display")])


class PixelClockLight(PixelClockEntity, LightEntity):
    _attr_name = None  # the device itself
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}

    @property
    def is_on(self) -> bool:
        return self.coordinator.settings.power

    @property
    def brightness(self) -> int:
        return round(self.coordinator.settings.brightness * 255 / 100)

    async def async_turn_on(self, **kwargs: Any) -> None:
        if ATTR_BRIGHTNESS in kwargs:
            await self.coordinator.async_set_brightness(max(1, round(kwargs[ATTR_BRIGHTNESS] * 100 / 255)))
        if not self.coordinator.settings.power:
            await self.coordinator.async_set_power(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_power(False)
