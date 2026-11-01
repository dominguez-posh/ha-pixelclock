"""Button entities: next app, dismiss notification."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import PixelClockConfigEntry
from .entity import PixelClockEntity


async def async_setup_entry(hass: HomeAssistant, entry: PixelClockConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    async_add_entities([NextAppButton(coordinator, "next_app"), DismissButton(coordinator, "dismiss")])


class NextAppButton(PixelClockEntity, ButtonEntity):
    async def async_press(self) -> None:
        self.coordinator.next_app()


class DismissButton(PixelClockEntity, ButtonEntity):
    async def async_press(self) -> None:
        self.coordinator.dismiss()
