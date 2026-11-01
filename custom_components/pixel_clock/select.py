"""Select entities: display mode and the panel's built-in clock face."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import protocol as proto
from . import render
from .const import MODES
from .coordinator import PixelClockConfigEntry
from .entity import PixelClockEntity


async def async_setup_entry(hass: HomeAssistant, entry: PixelClockConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    async_add_entities([
        ModeSelect(coordinator, "mode"),
        ClockStyleSelect(coordinator, "clock_style"),
        OrientationSelect(coordinator, "orientation"),
    ])


class ModeSelect(PixelClockEntity, SelectEntity):
    _attr_options = list(MODES)

    @property
    def current_option(self) -> str:
        return self.coordinator.settings.mode

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_settings(mode=option)


class OrientationSelect(PixelClockEntity, SelectEntity):
    """Landscape, portrait (panel turned left or right) or upside down; Home Assistant rotates the picture."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = list(render.ORIENTATIONS)

    @property
    def current_option(self) -> str:
        return self.coordinator.settings.orientation

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_settings(orientation=option)


class ClockStyleSelect(PixelClockEntity, SelectEntity):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = [str(i) for i in range(proto.CLOCK_STYLES)]

    @property
    def current_option(self) -> str:
        return str(self.coordinator.settings.clock_style)

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_settings(clock_style=int(option))
