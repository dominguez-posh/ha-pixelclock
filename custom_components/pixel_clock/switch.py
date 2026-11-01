"""Switch entities: rotate through the apps, one switch per app (shown on this panel or not)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigSubentry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import A_ENABLED
from .coordinator import PixelClockConfigEntry
from .entity import PixelClockEntity


async def async_setup_entry(hass: HomeAssistant, entry: PixelClockConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    # one switch per app; all on the panel's device (a device belongs to one subentry only)
    async_add_entities([
        AutoRotateSwitch(coordinator, "auto_rotate"),
        *(AppSwitch(coordinator, subentry) for subentry in coordinator.apps.values()),
        *(CustomPageSwitch(coordinator, name) for name in coordinator.settings.known_apps),
    ])
    # pages created later by automations (set_app) get their switch right away
    coordinator.on_new_app = lambda name: async_add_entities([CustomPageSwitch(coordinator, name)])
    entry.async_on_unload(lambda: setattr(coordinator, "on_new_app", None))


class AppSwitch(PixelClockEntity, SwitchEntity):
    """Show an app (configured as a subentry) on this panel."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, subentry: ConfigSubentry) -> None:
        super().__init__(coordinator, "app")
        self._subentry_id = subentry.subentry_id
        self._attr_unique_id = f"{coordinator.address}_app_{subentry.subentry_id}"
        self._attr_translation_placeholders = {"name": subentry.title}

    @property
    def _subentry(self) -> ConfigSubentry | None:
        return self.coordinator.config_entry.subentries.get(self._subentry_id)

    @property
    def is_on(self) -> bool:
        return bool(self._subentry and self._subentry.data.get(A_ENABLED, True))

    def _set(self, enabled: bool) -> None:
        if (subentry := self._subentry) is not None:
            self.hass.config_entries.async_update_subentry(
                self.coordinator.config_entry, subentry, data={**subentry.data, A_ENABLED: enabled}
            )

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._set(False)


class CustomPageSwitch(PixelClockEntity, SwitchEntity):
    """Show a page created by an automation (pixel_clock.set_app) on this panel."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, name: str) -> None:
        super().__init__(coordinator, "page_custom")
        self._app = name
        self._attr_unique_id = f"{coordinator.address}_page_app_{name}"
        self._attr_translation_placeholders = {"name": name.replace("_", " ").title()}

    @property
    def is_on(self) -> bool:
        return self._app not in self.coordinator.settings.hidden_apps

    @property
    def extra_state_attributes(self) -> dict:
        # active: the automation currently provides this page (e.g. the washing machine is running)
        return {"app": self._app, "active": self._app in self.coordinator.settings.custom_apps}

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_show_app(self._app, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_show_app(self._app, False)


class AutoRotateSwitch(PixelClockEntity, SwitchEntity):
    @property
    def is_on(self) -> bool:
        return self.coordinator.settings.auto_rotate

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_settings(auto_rotate=True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_settings(auto_rotate=False)
