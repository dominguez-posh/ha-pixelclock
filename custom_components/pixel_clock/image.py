"""Image entity: live preview of what the panel shows."""

from __future__ import annotations

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import PixelClockConfigEntry, PixelClockCoordinator
from .entity import PixelClockEntity


async def async_setup_entry(hass: HomeAssistant, entry: PixelClockConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities([PreviewImage(hass, entry.runtime_data)])


class PreviewImage(PixelClockEntity, ImageEntity):
    def __init__(self, hass: HomeAssistant, coordinator: PixelClockCoordinator) -> None:
        PixelClockEntity.__init__(self, coordinator, "preview")
        ImageEntity.__init__(self, hass)
        self._attr_content_type = "image/png"

    @property
    def available(self) -> bool:
        return self.coordinator.data.preview is not None

    @callback
    def _handle_coordinator_update(self) -> None:
        if (updated := self.coordinator.data.preview_updated) != self._attr_image_last_updated:
            self._attr_image_last_updated = updated
            self._attr_content_type = self.coordinator.data.preview[1]
        super()._handle_coordinator_update()

    async def async_image(self) -> bytes | None:
        preview = self.coordinator.data.preview
        return preview[0] if preview else None
