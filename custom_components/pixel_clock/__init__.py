"""Pixel Clock: iPixel Color LED panels (Bluetooth) as a smart home display."""

from __future__ import annotations

import logging
from types import MappingProxyType
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigSubentry
from homeassistant.const import ATTR_DEVICE_ID, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.typing import ConfigType

from . import effects
from .const import (
    A_ENABLED,
    A_TYPE,
    BUILTIN_APPS,
    CONF_CALENDAR_DAYS,
    CONF_CALENDARS,
    CONF_COLOR,
    CONF_DEFAULT_APPS,
    CONF_POWER,
    CONF_SENSORS,
    CONF_SHOW_CALENDAR,
    CONF_SHOW_CLOCK,
    CONF_SHOW_DATE,
    CONF_SHOW_POWER,
    CONF_SHOW_WEATHER,
    CONF_WEATHER,
    DEFAULT_CALENDAR_DAYS,
    DOMAIN,
    SUBENTRY_APP,
    T_CALENDAR,
    T_CLOCK,
    T_DATE,
    T_POWER,
    T_VALUE,
    T_WEATHER,
)
from .coordinator import Notification, PixelClockConfigEntry, PixelClockCoordinator

PLATFORMS = [
    Platform.BUTTON,
    Platform.IMAGE,
    Platform.LIGHT,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.TEXT,
]

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

_COLOR = vol.Any(cv.string, vol.All(vol.ExactSequence([cv.byte, cv.byte, cv.byte]), list))
_TARGET = {vol.Optional(ATTR_DEVICE_ID): vol.All(cv.ensure_list, [cv.string])}
_CONTENT = {
    vol.Required("text"): cv.string,
    vol.Optional("icon"): cv.string,
    vol.Optional("color"): _COLOR,
    vol.Optional("progress"): vol.Any(None, vol.All(vol.Coerce(float), vol.Range(min=0, max=100))),
    vol.Optional("progress_color"): _COLOR,
    vol.Optional("effect"): vol.In(effects.EFFECTS),
}
NOTIFY_SCHEMA = vol.Schema({
    **_TARGET, **_CONTENT,
    vol.Optional("duration"): vol.All(vol.Coerce(float), vol.Range(min=1, max=3600)),
})
SET_APP_SCHEMA = vol.Schema({
    **_TARGET, **_CONTENT,
    vol.Required("name"): cv.slug,
    vol.Optional("lifetime"): vol.All(vol.Coerce(float), vol.Range(min=10)),
})
REMOVE_APP_SCHEMA = vol.Schema({**_TARGET, vol.Required("name"): cv.slug})
DISMISS_SCHEMA = vol.Schema(_TARGET)


def _coordinators(hass: HomeAssistant, call: ServiceCall) -> list[PixelClockCoordinator]:
    entries = list(hass.config_entries.async_loaded_entries(DOMAIN))
    if device_ids := call.data.get(ATTR_DEVICE_ID):
        # the device identifier is (DOMAIN, Bluetooth address) = the entry's unique id
        registry = dr.async_get(hass)
        wanted = {
            ident
            for device_id in device_ids
            if (device := registry.async_get(device_id))
            for domain, ident in device.identifiers
            if domain == DOMAIN
        }
        entries = [e for e in entries if e.unique_id in wanted]
    if not entries:
        raise ServiceValidationError("No Pixel Clock found", translation_domain=DOMAIN, translation_key="no_device")
    return [e.runtime_data for e in entries]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    async def notify(call: ServiceCall) -> None:
        for coordinator in _coordinators(hass, call):
            coordinator.notify(Notification(
                text=call.data["text"],
                icon=call.data.get("icon"),
                color=call.data.get("color"),
                duration=call.data.get("duration"),
                progress=call.data.get("progress"),
                progress_color=call.data.get("progress_color"),
                effect=call.data.get("effect"),
            ))

    async def set_app(call: ServiceCall) -> None:
        name = call.data["name"]
        if name in BUILTIN_APPS:
            raise ServiceValidationError(f"'{name}' is a built-in app name")
        spec = {k: call.data[k] for k in ("text", "icon", "color", "progress", "progress_color", "effect")
                if k in call.data}
        for coordinator in _coordinators(hass, call):
            await coordinator.async_set_app(name, dict(spec), call.data.get("lifetime"))

    async def remove_app(call: ServiceCall) -> None:
        for coordinator in _coordinators(hass, call):
            await coordinator.async_remove_app(call.data["name"])

    async def dismiss(call: ServiceCall) -> None:
        for coordinator in _coordinators(hass, call):
            coordinator.dismiss()

    hass.services.async_register(DOMAIN, "notify", notify, NOTIFY_SCHEMA)
    hass.services.async_register(DOMAIN, "set_app", set_app, SET_APP_SCHEMA)
    hass.services.async_register(DOMAIN, "remove_app", remove_app, REMOVE_APP_SCHEMA)
    hass.services.async_register(DOMAIN, "dismiss", dismiss, DISMISS_SCHEMA)
    return True


def _app(kind: str, title: str, enabled: bool = True, **data: Any) -> ConfigSubentry:
    return ConfigSubentry(
        data=MappingProxyType({A_TYPE: kind, A_ENABLED: enabled, **data}),
        subentry_type=SUBENTRY_APP, title=title, unique_id=None,
    )


async def async_migrate_entry(hass: HomeAssistant, entry: PixelClockConfigEntry) -> bool:
    """Version 1 kept the built-in pages in the options; version 2 has one app subentry per page."""
    if entry.version > 2:
        return False
    if entry.version == 1:
        o = entry.options
        apps = [
            _app(T_CLOCK, "Uhr", o.get(CONF_SHOW_CLOCK, True)),
            _app(T_DATE, "Datum", o.get(CONF_SHOW_DATE, True)),
        ]
        if o.get(CONF_WEATHER):
            apps.append(_app(T_WEATHER, "Wetter", o.get(CONF_SHOW_WEATHER, True), entity=o[CONF_WEATHER]))
        if o.get(CONF_POWER):
            apps.append(_app(T_POWER, "Verbrauch", o.get(CONF_SHOW_POWER, True), entity=o[CONF_POWER]))
        if o.get(CONF_CALENDARS):
            apps.append(_app(T_CALENDAR, "Termine", o.get(CONF_SHOW_CALENDAR, True), calendars=list(o[CONF_CALENDARS]),
                             days=int(o.get(CONF_CALENDAR_DAYS, DEFAULT_CALENDAR_DAYS))))
        for entity_id in o.get(CONF_SENSORS, []):
            state = hass.states.get(entity_id)
            apps.append(_app(T_VALUE, state.name if state else entity_id, entity=entity_id))
        for app in apps:
            hass.config_entries.async_add_subentry(entry, app)
        options = {CONF_COLOR: o[CONF_COLOR]} if o.get(CONF_COLOR) else {}
        hass.config_entries.async_update_entry(
            entry, options=options, data={**entry.data, CONF_DEFAULT_APPS: True}, version=2
        )
        # the page switches and source selects of version 1 are replaced by one switch per app
        registry = er.async_get(hass)
        old = ("_page_clock", "_page_date", "_page_weather", "_page_power", "_page_calendar",
               "_source_weather", "_source_power", "_source_calendar")
        for ent in er.async_entries_for_config_entry(registry, entry.entry_id):
            if ent.unique_id.endswith(old):
                registry.async_remove(ent.entity_id)
        _LOGGER.info("%s: migrated %s pages to apps", entry.title, len(apps))
    return True


async def async_setup_entry(hass: HomeAssistant, entry: PixelClockConfigEntry) -> bool:
    if not entry.data.get(CONF_DEFAULT_APPS):
        # a new panel starts with clock and date; afterwards the user owns the list
        for app in (_app(T_CLOCK, "Uhr"), _app(T_DATE, "Datum")):
            hass.config_entries.async_add_subentry(entry, app)
        hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_DEFAULT_APPS: True})
    _detach_from_subentries(hass, entry)
    coordinator = PixelClockCoordinator(hass, entry)
    entry.runtime_data = coordinator
    coordinator.loaded_apps = set(coordinator.apps)
    await coordinator.async_start()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_entry_updated))
    return True


def _detach_from_subentries(hass: HomeAssistant, entry: PixelClockConfigEntry) -> None:
    """Entities and the device belong to the entry, not to an app subentry.

    f07d198 added the app switches with config_subentry_id, which moved the shared device into
    one app; re-create those entities without subentry and move the device back.
    """
    entities = er.async_get(hass)
    for ent in er.async_entries_for_config_entry(entities, entry.entry_id):
        if ent.config_subentry_id is not None:
            entities.async_remove(ent.entity_id)
    devices = dr.async_get(hass)
    for device in dr.async_entries_for_config_entry(devices, entry.entry_id):
        if device.config_subentry_id is not None:
            devices.async_update_device(device.id, new_config_subentry_id=None)


async def async_unload_entry(hass: HomeAssistant, entry: PixelClockConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_shutdown()
    return unloaded


async def _async_entry_updated(hass: HomeAssistant, entry: PixelClockConfigEntry) -> None:
    coordinator = entry.runtime_data
    if set(coordinator.apps) != coordinator.loaded_apps:
        # an app was added or deleted: its switch entity has to be created or removed
        await hass.config_entries.async_reload(entry.entry_id)
        return
    # options or an app's settings changed: no reconnect needed
    coordinator.async_track_entities()
    coordinator.async_update_listeners()
    coordinator.wake()
