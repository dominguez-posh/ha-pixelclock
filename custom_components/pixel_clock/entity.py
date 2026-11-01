"""Base entity."""

from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import PixelClockCoordinator


class PixelClockEntity(CoordinatorEntity[PixelClockCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: PixelClockCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._attr_translation_key = key
        self._attr_unique_id = f"{coordinator.address}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.address)},
            connections={(CONNECTION_BLUETOOTH, coordinator.address)},
            name=coordinator.config_entry.title,
            manufacturer="iPixel",
            model=f"LED panel {coordinator.width}x{coordinator.height}",
        )
