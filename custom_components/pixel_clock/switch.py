"""Switch entity: rotate through the apps automatically."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import PAGE_SWITCHES
from .coordinator import PixelClockConfigEntry
from .entity import PixelClockEntity


async def async_setup_entry(hass: HomeAssistant, entry: PixelClockConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    async_add_entities([
        AutoRotateSwitch(coordinator, "auto_rotate"),
        *(PageSwitch(coordinator, key, option) for option, key in PAGE_SWITCHES.items()),
    ])


class PageSwitch(PixelClockEntity, SwitchEntity):
    """Show a built-in page (clock, date, weather, power, appointments) on this panel."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, key: str, option: str) -> None:
        super().__init__(coordinator, key)
        self._option = option

    @property
    def is_on(self) -> bool:
        return self.coordinator.options.get(self._option, True)

    async def async_turn_on(self, **kwargs: Any) -> None:
        self.coordinator.async_set_option(self._option, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.coordinator.async_set_option(self._option, False)


class AutoRotateSwitch(PixelClockEntity, SwitchEntity):
    @property
    def is_on(self) -> bool:
        return self.coordinator.settings.auto_rotate

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_settings(auto_rotate=True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_settings(auto_rotate=False)
