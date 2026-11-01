"""Config flow: Bluetooth discovery or pick from the panels Home Assistant sees; options pick the apps."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak, async_discovered_service_info
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import callback
from homeassistant.helpers import selector

from . import protocol as proto
from .const import (
    CONF_CALENDAR_DAYS,
    CONF_CALENDARS,
    CONF_COLOR,
    CONF_HEIGHT,
    CONF_POWER,
    CONF_SENSORS,
    CONF_SHOW_CLOCK,
    CONF_SHOW_DATE,
    CONF_WEATHER,
    CONF_WIDTH,
    DEFAULT_CALENDAR_DAYS,
    DOMAIN,
)


def _is_panel(info: BluetoothServiceInfoBleak) -> bool:
    return (info.name or "").startswith(proto.NAME_PREFIX)


def _title(info: BluetoothServiceInfoBleak) -> str:
    return f"Pixel Clock {info.name.removeprefix(proto.NAME_PREFIX)[-4:]}"


def _entry_data(info: BluetoothServiceInfoBleak) -> dict[str, Any]:
    width, height = (
        proto.size_from_manufacturer_data(info.manufacturer_data.get(proto.MANUFACTURER_ID)) or proto.DEFAULT_SIZE
    )
    return {CONF_WIDTH: width, CONF_HEIGHT: height}


class PixelClockConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._discovery: BluetoothServiceInfoBleak | None = None
        self._discovered: dict[str, BluetoothServiceInfoBleak] = {}

    async def async_step_bluetooth(self, discovery_info: BluetoothServiceInfoBleak) -> ConfigFlowResult:
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        if not _is_panel(discovery_info):
            return self.async_abort(reason="not_supported")
        self._discovery = discovery_info
        self.context["title_placeholders"] = {"name": _title(discovery_info)}
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        assert self._discovery is not None
        if user_input is not None:
            return self.async_create_entry(title=_title(self._discovery), data=_entry_data(self._discovery))
        self._set_confirm_only()
        data = _entry_data(self._discovery)
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={
                "name": _title(self._discovery),
                "address": self._discovery.address,
                "size": f"{data[CONF_WIDTH]}x{data[CONF_HEIGHT]}",
            },
        )

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            info = self._discovered[user_input[CONF_ADDRESS]]
            await self.async_set_unique_id(info.address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=_title(info), data=_entry_data(info))

        configured = self._async_current_ids(include_ignore=False)
        for info in async_discovered_service_info(self.hass, connectable=True):
            if info.address not in configured and _is_panel(info):
                self._discovered[info.address] = info
        if not self._discovered:
            return self.async_abort(reason="no_devices_found")
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_ADDRESS): vol.In({a: f"{_title(i)} ({a})" for a, i in self._discovered.items()})
            }),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> PixelClockOptionsFlow:
        return PixelClockOptionsFlow()


def _entity(domain: str | list[str], multiple: bool = False, device_class: str | None = None) -> selector.EntitySelector:
    config = selector.EntitySelectorConfig(domain=domain, multiple=multiple)
    if device_class:
        config["device_class"] = device_class
    return selector.EntitySelector(config)


class PixelClockOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            # keep options set on the device page (page switches); fields of this form are replaced,
            # so clearing an optional entity here removes it
            form_keys = {CONF_SHOW_CLOCK, CONF_SHOW_DATE, CONF_WEATHER, CONF_POWER, CONF_CALENDARS,
                         CONF_CALENDAR_DAYS, CONF_SENSORS, CONF_COLOR}
            kept = {k: v for k, v in self.config_entry.options.items() if k not in form_keys}
            return self.async_create_entry(data={**kept, **user_input})
        o = self.config_entry.options

        def opt(key: str) -> dict[str, Any]:
            return {"suggested_value": o.get(key)} if o.get(key) else {}

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(CONF_SHOW_CLOCK, default=o.get(CONF_SHOW_CLOCK, True)): bool,
                vol.Required(CONF_SHOW_DATE, default=o.get(CONF_SHOW_DATE, True)): bool,
                vol.Optional(CONF_WEATHER, description=opt(CONF_WEATHER)): _entity("weather"),
                vol.Optional(CONF_POWER, description=opt(CONF_POWER)): _entity("sensor", device_class="power"),
                vol.Optional(CONF_CALENDARS, description=opt(CONF_CALENDARS)): _entity("calendar", multiple=True),
                vol.Required(CONF_CALENDAR_DAYS, default=o.get(CONF_CALENDAR_DAYS, DEFAULT_CALENDAR_DAYS)):
                    selector.NumberSelector(selector.NumberSelectorConfig(min=1, max=14, mode=selector.NumberSelectorMode.BOX)),
                vol.Optional(CONF_SENSORS, description=opt(CONF_SENSORS)):
                    _entity(["sensor", "binary_sensor", "input_number", "counter"], multiple=True),
                vol.Optional(CONF_COLOR, description=opt(CONF_COLOR)): selector.ColorRGBSelector(),
            }),
        )
