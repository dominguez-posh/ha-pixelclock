"""Config flow: Bluetooth discovery or pick from the panels Home Assistant sees; apps are subentries."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak, async_discovered_service_info
from homeassistant.config_entries import (
    SOURCE_RECONFIGURE,
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    OptionsFlow,
    SubentryFlowResult,
)
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import selector

from . import effects, icons
from . import protocol as proto
from .const import (
    A_ABOVE,
    A_ACTIVE_STATES,
    A_CALENDARS,
    A_COLOR,
    A_DAYS,
    A_DECIMALS,
    A_DONE_TEXT,
    A_EFFECT,
    A_ENABLED,
    A_ENTITY,
    A_ICON,
    A_LABEL,
    A_MAX,
    A_MIN,
    A_OFF_DELAY,
    A_PROGRESS,
    A_PROGRESS_ENTITY,
    A_SECONDS,
    A_TEXT,
    A_TYPE,
    A_UNIT,
    A_WEEKDAY_BAR,
    APP_TYPES,
    CONF_COLOR,
    CONF_HEIGHT,
    CONF_WIDTH,
    DEFAULT_CALENDAR_DAYS,
    DOMAIN,
    ICON_AUTO,
    ICON_NONE,
    SUBENTRY_APP,
    T_CALENDAR,
    T_CLOCK,
    T_DATE,
    T_POWER,
    T_STATUS,
    T_TEXT,
    T_VALUE,
    T_WEATHER,
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
    VERSION = 2  # 2: pages are app subentries instead of options

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

    @classmethod
    @callback
    def async_get_supported_subentry_types(cls, config_entry: ConfigEntry) -> dict[str, type[ConfigSubentryFlow]]:
        return {SUBENTRY_APP: AppSubentryFlow}


def _entity(domain: str | list[str] | None = None, multiple: bool = False,
            device_class: str | None = None) -> selector.EntitySelector:
    config = selector.EntitySelectorConfig(multiple=multiple)
    if domain:
        config["domain"] = domain
    if device_class:
        config["device_class"] = device_class
    return selector.EntitySelector(config)


def _number(minimum: float, maximum: float, step: float = 1, unit: str | None = None) -> selector.NumberSelector:
    config = selector.NumberSelectorConfig(min=minimum, max=maximum, step=step, mode=selector.NumberSelectorMode.BOX)
    if unit:
        config["unit_of_measurement"] = unit
    return selector.NumberSelector(config)


ICON_SELECTOR = selector.SelectSelector(selector.SelectSelectorConfig(
    options=[ICON_AUTO, ICON_NONE, *icons.BUILTIN_NAMES],
    custom_value=True,  # LaMetric icon id or an image file
    mode=selector.SelectSelectorMode.DROPDOWN,
    translation_key="icon",
    sort=False,
))
EFFECT_SELECTOR = selector.SelectSelector(selector.SelectSelectorConfig(
    options=list(effects.EFFECTS), mode=selector.SelectSelectorMode.DROPDOWN, translation_key="effect",
))
TYPE_SELECTOR = selector.SelectSelector(selector.SelectSelectorConfig(
    options=list(APP_TYPES), mode=selector.SelectSelectorMode.LIST, translation_key="app_type",
))
STATES_SELECTOR = selector.TextSelector(selector.TextSelectorConfig(multiple=True))
TEXT_SELECTOR = selector.TextSelector(selector.TextSelectorConfig(multiline=False))

# default page names per type (the subentry title, editable)
DEFAULT_TITLES = {
    "de": {T_CLOCK: "Uhr", T_DATE: "Datum", T_WEATHER: "Wetter", T_VALUE: "Wert", T_POWER: "Verbrauch",
           T_STATUS: "Status", T_TEXT: "Text", T_CALENDAR: "Termine"},
    "en": {T_CLOCK: "Clock", T_DATE: "Date", T_WEATHER: "Weather", T_VALUE: "Value", T_POWER: "Power",
           T_STATUS: "Status", T_TEXT: "Text", T_CALENDAR: "Appointments"},
}


def _type_fields(kind: str, d: Mapping[str, Any]) -> dict:
    """Fields of one app type; d holds the current values (reconfigure) or {}."""

    def opt(key: str, default: Any = None):
        value = d.get(key, default)
        return vol.Optional(key, description={"suggested_value": value} if value not in (None, "", []) else {})

    def req(key: str, default: Any):
        return vol.Required(key, default=d.get(key, default))

    if kind == T_CLOCK:
        return {req(A_SECONDS, True): bool, req(A_WEEKDAY_BAR, True): bool}
    if kind == T_WEATHER:
        return {req(A_ENTITY, None) if d.get(A_ENTITY) else vol.Required(A_ENTITY): _entity("weather")}
    if kind == T_POWER:
        return {req(A_ENTITY, None) if d.get(A_ENTITY) else vol.Required(A_ENTITY): _entity("sensor", device_class="power")}
    if kind == T_VALUE:
        return {
            req(A_ENTITY, None) if d.get(A_ENTITY) else vol.Required(A_ENTITY): _entity(),
            opt(A_LABEL): TEXT_SELECTOR,
            opt(A_UNIT): TEXT_SELECTOR,
            opt(A_DECIMALS): _number(0, 3),
            req(A_PROGRESS, False): bool,
            req(A_MIN, 0): _number(-100000, 100000, 0.1),
            req(A_MAX, 100): _number(-100000, 100000, 0.1),
        }
    if kind == T_STATUS:
        return {
            req(A_ENTITY, None) if d.get(A_ENTITY) else vol.Required(A_ENTITY): _entity(),
            opt(A_ACTIVE_STATES): STATES_SELECTOR,
            opt(A_ABOVE): _number(-100000, 100000, 0.1),
            req(A_OFF_DELAY, 0): _number(0, 60, 1, "min"),
            opt(A_TEXT): TEXT_SELECTOR,
            opt(A_PROGRESS_ENTITY): _entity(),
            opt(A_DONE_TEXT): TEXT_SELECTOR,
        }
    if kind == T_TEXT:
        return {req(A_TEXT, None) if d.get(A_TEXT) else vol.Required(A_TEXT): TEXT_SELECTOR}
    if kind == T_CALENDAR:
        return {
            req(A_CALENDARS, None) if d.get(A_CALENDARS) else vol.Required(A_CALENDARS): _entity("calendar", multiple=True),
            req(A_DAYS, DEFAULT_CALENDAR_DAYS): _number(1, 14),
        }
    return {}


class AppSubentryFlow(ConfigSubentryFlow):
    """Add or edit one app (page) of a panel: pick the type, then what it shows and how it looks."""

    def __init__(self) -> None:
        self._kind: str | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        if user_input is not None:
            self._kind = user_input[A_TYPE]
            return await self.async_step_app()
        return self.async_show_form(step_id="user", data_schema=vol.Schema({vol.Required(A_TYPE): TYPE_SELECTOR}))

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        self._kind = self._get_reconfigure_subentry().data.get(A_TYPE, T_TEXT)
        return await self.async_step_app()

    async def async_step_app(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        kind = self._kind
        reconfigure = self.source == SOURCE_RECONFIGURE
        current = dict(self._get_reconfigure_subentry().data) if reconfigure else {}
        lang = "de" if (self.hass.config.language or "").startswith("de") else "en"
        errors: dict[str, str] = {}
        if user_input is not None:
            if kind == T_STATUS and not user_input.get(A_ACTIVE_STATES) and user_input.get(A_ABOVE) is None:
                errors["base"] = "status_condition"
            else:
                name = user_input.pop(CONF_NAME, None) or DEFAULT_TITLES[lang][kind]
                data = {A_TYPE: kind, A_ENABLED: current.get(A_ENABLED, True), **user_input}
                for key in (A_DECIMALS, A_DAYS, A_OFF_DELAY):
                    if data.get(key) is not None:
                        data[key] = int(data[key])
                if reconfigure:
                    return self.async_update_and_abort(
                        self._get_entry(), self._get_reconfigure_subentry(), title=name, data=data
                    )
                return self.async_create_entry(title=name, data=data)

        title = self._get_reconfigure_subentry().title if reconfigure else DEFAULT_TITLES[lang][kind]
        fields: dict = {vol.Required(CONF_NAME, default=title): TEXT_SELECTOR}
        fields.update(_type_fields(kind, current))
        if kind != T_CLOCK:
            fields[vol.Required(A_ICON, default=current.get(A_ICON, ICON_AUTO))] = ICON_SELECTOR
        fields[vol.Optional(A_COLOR, description={"suggested_value": current[A_COLOR]} if current.get(A_COLOR) else {})] = \
            selector.ColorRGBSelector()
        fields[vol.Required(A_EFFECT, default=current.get(A_EFFECT, "none"))] = EFFECT_SELECTOR
        return self.async_show_form(
            step_id="app",
            data_schema=vol.Schema(fields),
            errors=errors,
            description_placeholders={"type": kind},
        )


class PixelClockOptionsFlow(OptionsFlow):
    """Panel-wide options; the pages themselves are apps (subentries)."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        color = self.config_entry.options.get(CONF_COLOR)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional(CONF_COLOR, description={"suggested_value": color} if color else {}):
                    selector.ColorRGBSelector(),
            }),
        )
