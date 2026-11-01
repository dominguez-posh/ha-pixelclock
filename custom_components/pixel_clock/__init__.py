"""Pixel Clock: iPixel Color LED panels (Bluetooth) as a smart home display."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.const import ATTR_DEVICE_ID, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.typing import ConfigType

from .const import BUILTIN_APPS, DOMAIN
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

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

_COLOR = vol.Any(cv.string, vol.All(vol.ExactSequence([cv.byte, cv.byte, cv.byte]), list))
_TARGET = {vol.Optional(ATTR_DEVICE_ID): vol.All(cv.ensure_list, [cv.string])}
_CONTENT = {
    vol.Required("text"): cv.string,
    vol.Optional("icon"): cv.string,
    vol.Optional("color"): _COLOR,
    vol.Optional("progress"): vol.Any(None, vol.All(vol.Coerce(float), vol.Range(min=0, max=100))),
    vol.Optional("progress_color"): _COLOR,
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
            ))

    async def set_app(call: ServiceCall) -> None:
        name = call.data["name"]
        if name in BUILTIN_APPS:
            raise ServiceValidationError(f"'{name}' is a built-in app name")
        spec = {k: call.data[k] for k in ("text", "icon", "color", "progress", "progress_color") if k in call.data}
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


async def async_setup_entry(hass: HomeAssistant, entry: PixelClockConfigEntry) -> bool:
    coordinator = PixelClockCoordinator(hass, entry)
    entry.runtime_data = coordinator
    await coordinator.async_start()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: PixelClockConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_shutdown()
    return unloaded


async def _async_options_updated(hass: HomeAssistant, entry: PixelClockConfigEntry) -> None:
    # options only change which apps are shown: no reload (and no reconnect) needed
    entry.runtime_data.async_track_entities()
    entry.runtime_data.async_update_listeners()  # page switches and source selects on the device page
    entry.runtime_data.wake()
