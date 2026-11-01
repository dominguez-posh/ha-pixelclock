"""Select entities: display mode, orientation, clock face and the sources of the built-in pages."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import protocol as proto
from . import render
from .const import CONF_CALENDARS, CONF_POWER, CONF_WEATHER, MODES
from .coordinator import PixelClockConfigEntry
from .entity import PixelClockEntity


async def async_setup_entry(hass: HomeAssistant, entry: PixelClockConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    async_add_entities([
        ModeSelect(coordinator, "mode"),
        ClockStyleSelect(coordinator, "clock_style"),
        OrientationSelect(coordinator, "orientation"),
        SourceSelect(coordinator, "source_weather", CONF_WEATHER, "weather"),
        SourceSelect(coordinator, "source_power", CONF_POWER, "sensor", "power"),
        SourceSelect(coordinator, "source_calendar", CONF_CALENDARS, "calendar", as_list=True),
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


NONE = "–"


class SourceSelect(PixelClockEntity, SelectEntity):
    """Which entity feeds a built-in page; the options are the matching entities by name."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, key: str, option: str, domain: str, device_class: str | None = None,
                 as_list: bool = False) -> None:
        super().__init__(coordinator, key)
        self._option = option
        self._domain = domain
        self._device_class = device_class
        self._as_list = as_list  # calendars are stored as a list (the options flow can pick several)

    def _candidates(self) -> dict[str, str]:
        """Label -> entity id; labels are friendly names, made unique with the entity id when needed."""
        states = [
            st for st in self.hass.states.async_all(self._domain)
            if self._device_class is None or st.attributes.get("device_class") == self._device_class
        ]
        names = [st.name for st in states]
        return {
            (st.name if names.count(st.name) == 1 else f"{st.name} ({st.entity_id})"): st.entity_id
            for st in sorted(states, key=lambda st: st.name.lower())
        }

    def _current_id(self) -> str | None:
        value = self.coordinator.options.get(self._option)
        if isinstance(value, list):
            return value[0] if value else None
        return value or None

    @property
    def options(self) -> list[str]:
        labels = list(self._candidates())
        current = self._current_id()
        if current and current not in self._candidates().values():
            labels.append(current)  # configured entity that is gone or renamed
        return [NONE, *labels]

    @property
    def current_option(self) -> str:
        current = self._current_id()
        if not current:
            return NONE
        for label, entity_id in self._candidates().items():
            if entity_id == current:
                return label
        return current

    async def async_select_option(self, option: str) -> None:
        entity_id = None if option == NONE else self._candidates().get(option, option)
        if self._as_list:
            self.coordinator.async_set_option(self._option, [entity_id] if entity_id else None)
        else:
            self.coordinator.async_set_option(self._option, entity_id)
