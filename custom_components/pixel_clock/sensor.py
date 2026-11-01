"""Sensor entities: current app, panel info."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import PixelClockConfigEntry
from .entity import PixelClockEntity


async def async_setup_entry(hass: HomeAssistant, entry: PixelClockConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    async_add_entities([CurrentAppSensor(coordinator, "current_app"), PanelSensor(coordinator, "panel")])


class CurrentAppSensor(PixelClockEntity, SensorEntity):
    @property
    def native_value(self) -> str | None:
        return self.coordinator.data.current_app

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "apps": self.coordinator.app_names,
            "notifications_queued": self.coordinator.data.notifications,
            "custom_apps": list(self.coordinator.settings.custom_apps),
        }


class PanelSensor(PixelClockEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self) -> str:
        return f"{self.coordinator.width}x{self.coordinator.height}"

    @property
    def extra_state_attributes(self) -> dict:
        info = self.coordinator.client.device_info
        return {
            "connected": self.coordinator.connected,
            "device_type": info.device_type if info else None,
            "info_raw": info.raw.hex(" ") if info else None,
        }
