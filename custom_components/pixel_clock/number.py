"""Number entity: how long each app is shown."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import MAX_APP_SECONDS, MIN_APP_SECONDS
from .coordinator import PixelClockConfigEntry
from .entity import PixelClockEntity


async def async_setup_entry(hass: HomeAssistant, entry: PixelClockConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities([AppDurationNumber(entry.runtime_data, "app_duration")])


class AppDurationNumber(PixelClockEntity, NumberEntity):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = MIN_APP_SECONDS
    _attr_native_max_value = MAX_APP_SECONDS
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS

    @property
    def native_value(self) -> int:
        return self.coordinator.settings.app_seconds

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_settings(app_seconds=int(value))
