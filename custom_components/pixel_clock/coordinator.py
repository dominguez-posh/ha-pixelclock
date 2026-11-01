"""Display loop for one panel: rotates apps, shows notifications, keeps the BLE connection."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import CALLBACK_TYPE, Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store
from homeassistant.helpers.template import Template
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util
from PIL import Image

from . import icons, render
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
    APP_CLOCK,
    APP_PREFIX,
    CALENDAR_REFRESH,
    CONF_COLOR,
    CONF_HEIGHT,
    CONF_WIDTH,
    DEFAULT_APP_SECONDS,
    DEFAULT_BRIGHTNESS,
    DEFAULT_CALENDAR_DAYS,
    DEFAULT_NOTIFY_SECONDS,
    DOMAIN,
    ICON_AUTO,
    ICON_NONE,
    MODE_APPS,
    MODE_CLOCK,
    RETRY_SECONDS,
    SUBENTRY_APP,
    T_CALENDAR,
    T_CLOCK,
    T_DATE,
    T_POWER,
    T_STATUS,
    T_TEXT,
    T_VALUE,
    T_WEATHER,
    TIME_SYNC_INTERVAL,
    TODAY,
    TOMORROW,
    WEEKDAYS,
    WEEKDAYS_SHORT,
)
from .device import PixelClockClient
from .render import Line, Screen

_LOGGER = logging.getLogger(__name__)

LIVE_REFRESH_SECONDS = 1.0

BLE_ERRORS = (BleakError, TimeoutError, ConnectionError, EOFError)

type PixelClockConfigEntry = ConfigEntry[PixelClockCoordinator]


@dataclass
class Notification:
    text: str
    icon: str | None = None
    color: Any = None
    duration: float | None = None
    progress: float | None = None
    progress_color: Any = None
    effect: str | None = None


@dataclass
class DisplayState:
    current_app: str | None = None
    preview: tuple[bytes, str] | None = None
    preview_updated: datetime | None = None
    notifications: int = 0


@dataclass
class _Shown:
    key: str
    digest: str
    cycle_ms: int
    valid_until: datetime | None = None


@dataclass
class _Settings:
    power: bool = True
    brightness: int = DEFAULT_BRIGHTNESS
    mode: str = MODE_APPS
    clock_style: int = 1
    orientation: str = "landscape"
    auto_rotate: bool = True
    app_seconds: int = DEFAULT_APP_SECONDS
    custom_apps: dict[str, dict[str, Any]] = field(default_factory=dict)
    # every custom page ever set (one switch each on the device page) and the ones switched off
    known_apps: list[str] = field(default_factory=list)
    hidden_apps: list[str] = field(default_factory=list)


class PixelClockCoordinator(DataUpdateCoordinator[DisplayState]):
    config_entry: PixelClockConfigEntry

    def __init__(self, hass: HomeAssistant, entry: PixelClockConfigEntry) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=entry.title, update_interval=None)
        self.address: str = entry.unique_id
        self.width: int = entry.data.get(CONF_WIDTH, proto.DEFAULT_SIZE[0])
        self.height: int = entry.data.get(CONF_HEIGHT, proto.DEFAULT_SIZE[1])
        self.client = PixelClockClient(entry.title, lambda: dt_util.now().replace(tzinfo=None))
        self.settings = _Settings()
        self.data = DisplayState()
        self._store: Store[dict[str, Any]] = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")
        self._wake = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._notifications: list[Notification] = []
        self._dismiss = False
        self._app_index = -1
        self._app_until = 0.0
        self._advance = False
        self._shown: _Shown | None = None
        self._native_clock_shown = False
        self._settings_applied = False
        self._last_time_sync: datetime | None = None
        self._calendar_cache: dict[tuple[tuple[str, ...], int], tuple[datetime | None, list[dict[str, Any]]]] = {}
        self._status: dict[str, dict[str, Any]] = {}
        self._entity_apps: dict[str, set[str]] = {}
        self._icons: dict[str, Image.Image | None] = {}
        self._icon_dir = Path(hass.config.path(".storage", f"{DOMAIN}_icons"))
        self._unsub_states: CALLBACK_TYPE | None = None
        self.on_new_app: Callable[[str], None] | None = None  # set by the switch platform
        self.loaded_apps: set[str] = set()  # app subentry ids the entities were created for
        self._last_upload = 0.0
        self._preview_seq = 0

    # ---- lifecycle -------------------------------------------------------------------------

    async def async_start(self) -> None:
        if data := await self._store.async_load():
            known = _Settings.__dataclass_fields__
            self.settings = _Settings(**{k: v for k, v in data.items() if k in known})
        for name in self.settings.custom_apps:  # pages set before switches existed
            if name not in self.settings.known_apps:
                self.settings.known_apps.append(name)
        self.async_track_entities()
        self._task = self.config_entry.async_create_background_task(
            self.hass, self._run(), f"{DOMAIN} display {self.address}"
        )

    async def async_shutdown(self) -> None:
        await super().async_shutdown()
        if self._unsub_states:
            self._unsub_states()
            self._unsub_states = None
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        await self.client.async_disconnect()

    async def _save(self) -> None:
        await self._store.async_save(self.settings.__dict__)

    def wake(self) -> None:
        self._wake.set()

    @callback
    def async_track_entities(self) -> None:
        """Listen to the entities the apps show, so the app on screen follows them live."""
        if self._unsub_states:
            self._unsub_states()
            self._unsub_states = None
        self._entity_apps = {}
        for sid, sub in self.apps.items():
            for key in (A_ENTITY, A_PROGRESS_ENTITY):
                if entity := sub.data.get(key):
                    self._entity_apps.setdefault(entity, set()).add(f"{APP_PREFIX}{sid}")
        if self._entity_apps:
            self._unsub_states = async_track_state_change_event(
                self.hass, list(self._entity_apps), self._on_state_change
            )
        self._evaluate_status()

    @callback
    def _on_state_change(self, event: Event[EventStateChangedData]) -> None:
        self._evaluate_status()
        if self.data.current_app in self._entity_apps.get(event.data["entity_id"], ()):
            self.wake()

    @property
    def options(self) -> dict[str, Any]:
        return self.config_entry.options

    @property
    def connected(self) -> bool:
        return self.client.connected

    @property
    def language(self) -> str:
        return "de" if (self.hass.config.language or "").startswith("de") else "en"

    def _ble_device(self) -> BLEDevice | None:
        return bluetooth.async_ble_device_from_address(self.hass, self.address, connectable=True)

    # ---- display loop ----------------------------------------------------------------------

    async def _run(self) -> None:
        failures = 0
        while True:
            try:
                await self._step()
                failures = 0
            except asyncio.CancelledError:
                raise
            except BLE_ERRORS as err:
                delay = RETRY_SECONDS[min(failures, len(RETRY_SECONDS) - 1)]
                failures += 1
                if failures == 1:
                    _LOGGER.warning("%s: %s, retrying", self.name, err or type(err).__name__)
                else:
                    _LOGGER.debug("%s: %s, retry in %s s", self.name, err or type(err).__name__, delay)
                self._shown = None
                self._native_clock_shown = False
                self._settings_applied = False
                await self.client.async_disconnect()
                self._set_available(False)
                await self._sleep(delay)
            except Exception:
                _LOGGER.exception("%s: display loop error", self.name)
                self._shown = None
                await self._sleep(30)

    async def _sleep(self, seconds: float) -> None:
        """Wait until woken (settings changed, new notification ...) or the timeout passes."""
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._wake.wait(), max(0.05, seconds))
        self._wake.clear()

    def _set_available(self, available: bool) -> None:
        if self.last_update_success != available:
            self.last_update_success = available
            self.async_update_listeners()

    async def _step(self) -> None:
        if not self.settings.power:
            await self._sleep(3600)
            return

        now = dt_util.now()
        if self._last_time_sync is None or now - self._last_time_sync > TIME_SYNC_INTERVAL:
            await self.client.async_sync_time(self._ble_device())
            self._last_time_sync = now
            self._native_clock_shown = False  # the clock face shows the new date
            self._adopt_panel_size()
        if not self._settings_applied:
            # the panel may have been unplugged: it then starts with its own brightness
            await self.client.async_command(self._ble_device(), proto.set_brightness(self.settings.brightness))
            self._settings_applied = True
        self._set_available(True)
        self._evaluate_status()
        await self._refresh_calendars()

        if self._notifications:
            await self._show_notification(self._notifications[0])
            return

        if self.settings.mode == MODE_CLOCK:
            if not self._native_clock_shown:
                await self.client.async_command(
                    self._ble_device(), proto.set_clock_mode(self.settings.clock_style, now.replace(tzinfo=None))
                )
                self._native_clock_shown = True
                self._shown = None
            # the panel draws its own clock face: the preview only approximates it
            approx = self._clock(now)
            self._schedule_preview(approx)
            self._publish(APP_CLOCK)
            await self._sleep(60 - now.second + 0.05)
            return

        await self._show_apps()

    def _adopt_panel_size(self) -> None:
        info = self.client.device_info
        if info is None or (info.width, info.height) == (self.width, self.height):
            return
        _LOGGER.info("%s: panel reports %sx%s", self.name, info.width, info.height)
        self.width, self.height = info.width, info.height
        self.hass.config_entries.async_update_entry(
            self.config_entry, data={**self.config_entry.data, CONF_WIDTH: info.width, CONF_HEIGHT: info.height}
        )

    async def _show_notification(self, note: Notification) -> None:
        screen = await self._screen_for(
            note.text, note.icon, note.color, note.progress, note.progress_color, default_icon="bell",
            effect=note.effect,
        )
        rendered = await self._send(f"notify:{id(note)}", screen)
        seconds = note.duration or max(DEFAULT_NOTIFY_SECONDS, rendered.scroll_ms / 1000)
        self._publish("notification")
        end = time.monotonic() + seconds
        self._dismiss = False
        while (left := end - time.monotonic()) > 0 and not self._dismiss:
            await self._sleep(left)
        if self._notifications and self._notifications[0] is note:
            self._notifications.pop(0)
        self._app_until = 0  # continue with the next app

    async def _show_apps(self) -> None:
        apps = self._app_names()
        mono = time.monotonic()
        current = apps[self._app_index] if 0 <= self._app_index < len(apps) else None
        if current is None or self._advance or (self.settings.auto_rotate and mono >= self._app_until):
            self._app_index = (self._app_index + 1) % len(apps)
            current = apps[self._app_index]
            self._app_until = 0
            self._advance = False
        elif self._shown is not None and self._shown.key == current:
            # live update of the page on screen: at most one upload per LIVE_REFRESH_SECONDS
            if (wait := self._last_upload + LIVE_REFRESH_SECONDS - time.monotonic()) > 0:
                await asyncio.sleep(wait)

        shown = self._shown
        if shown is not None and shown.key == current and shown.valid_until and dt_util.now() < shown.valid_until:
            # still on screen and still correct (clock with running seconds): sending it again
            # would restart the GIF and make the seconds jump
            scroll_ms = 0
        else:
            rendered = await self._send(current, await self._build(current))
            scroll_ms = rendered.scroll_ms
        if self._app_until == 0:
            # counted from the end of the upload, which can take seconds for scrolling text
            seconds = max(self.settings.app_seconds, scroll_ms / 1000)
            self._app_until = time.monotonic() + seconds
        self._publish(current)

        timeout = self._app_until - time.monotonic() if self.settings.auto_rotate else 30
        if self._shown is not None and self._shown.key == current and self._shown.valid_until:
            timeout = min(timeout, (self._shown.valid_until - dt_util.now()).total_seconds() + 0.05)
        elif current == APP_CLOCK:
            now = dt_util.now()
            timeout = min(timeout, 60 - now.second - now.microsecond / 1e6 + 0.05)
        await self._sleep(min(timeout, 30))

    async def _send(self, key: str, what: Screen | render.Rendered) -> render.Rendered:
        """Render (in the executor) and upload, unless the panel already shows exactly this."""
        rendered, data, is_gif, digest = await self.hass.async_add_executor_job(self._render, what)
        if self._shown is not None and self._shown.key == key and self._shown.digest == digest:
            return rendered
        await self.client.async_send_image(self._ble_device(), data, is_gif)
        self._last_upload = time.monotonic()
        self._shown = _Shown(key, digest, rendered.cycle_ms, rendered.valid_until)
        self._native_clock_shown = False
        self._schedule_preview(rendered)
        return rendered

    def _schedule_preview(self, rendered: render.Rendered) -> None:
        """Build the preview in the background, so it never delays the panel or the state."""
        self._preview_seq += 1
        seq = self._preview_seq

        async def build() -> None:
            preview = await self.hass.async_add_executor_job(render.preview, rendered)
            if seq == self._preview_seq:  # a newer picture may have been sent meanwhile
                self.data.preview = preview
                self.data.preview_updated = dt_util.utcnow()
                self.async_update_listeners()

        self.config_entry.async_create_background_task(self.hass, build(), f"{DOMAIN} preview")

    def _render(self, what: Screen | render.Rendered) -> tuple[render.Rendered, bytes, bool, str]:
        rendered = what if isinstance(what, render.Rendered) else render.render_screen(what, *self.view_size)
        data, is_gif = render.encode(render.to_panel(rendered, self.settings.orientation))
        return rendered, data, is_gif, hashlib.sha1(data).hexdigest()

    def _publish(self, app: str) -> None:
        self.data.current_app = app
        self.data.notifications = len(self._notifications)
        self.async_set_updated_data(self.data)

    # ---- apps --------------------------------------------------------------------------------
    # Apps are config subentries of the panel's entry (type "app"); pages set by automations
    # through pixel_clock.set_app are kept in settings.custom_apps.

    @property
    def apps(self) -> dict[str, ConfigSubentry]:
        return {sid: sub for sid, sub in self.config_entry.subentries.items() if sub.subentry_type == SUBENTRY_APP}

    def _app_names(self) -> list[str]:
        names = [
            f"{APP_PREFIX}{sid}" for sid, sub in self.apps.items()
            if sub.data.get(A_ENABLED, True) and self._app_available(sid, sub.data)
        ]
        now = dt_util.utcnow()
        for name, app in list(self.settings.custom_apps.items()):
            if (expires := app.get("expires")) and dt_util.parse_datetime(expires) < now:
                del self.settings.custom_apps[name]
                continue
            if name not in self.settings.hidden_apps:
                names.append(f"app:{name}")
        return names or [APP_CLOCK]

    def _app_available(self, sid: str, data: Mapping[str, Any]) -> bool:
        kind = data.get(A_TYPE)
        if kind in (T_WEATHER, T_VALUE, T_POWER):
            return self._usable(data.get(A_ENTITY))
        if kind == T_STATUS:
            return self._status.get(sid, {}).get("active", False)
        if kind == T_CALENDAR:
            return self._next_event(data) is not None
        return True

    def _usable(self, entity_id: str | None) -> bool:
        if not entity_id:
            return False
        state = self.hass.states.get(entity_id)
        return state is not None and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN)

    @property
    def app_names(self) -> list[str]:
        return self._app_names()

    def app_title(self, key: str | None) -> str | None:
        """Readable name of an app key for the current-app sensor."""
        if key and key.startswith(APP_PREFIX) and (sub := self.apps.get(key.removeprefix(APP_PREFIX))):
            return sub.title
        return key.removeprefix("app:") if key else key

    def _color(self) -> render.RGB:
        return render.parse_color(self.options.get(CONF_COLOR))

    # status apps: active while the entity is in one of the states or above a value, kept for
    # off_delay minutes after it stops (washing machines pause); done_text is shown when it ends

    @callback
    def _evaluate_status(self) -> None:
        mono = time.monotonic()
        for sid, sub in self.apps.items():
            data = sub.data
            if data.get(A_TYPE) != T_STATUS:
                continue
            rec = self._status.setdefault(sid, {"active": False, "last": 0.0})
            if self._status_now(data):
                rec["last"] = mono
                active = True
            else:
                active = rec["active"] and mono - rec["last"] < float(data.get(A_OFF_DELAY, 0)) * 60
            if rec["active"] and not active and data.get(A_DONE_TEXT) and data.get(A_ENABLED, True):
                self.notify(Notification(text=self._template(data[A_DONE_TEXT]), icon=data.get(A_ICON) or "check",
                                         color=[0, 200, 60], duration=30, effect=data.get(A_EFFECT)))
            rec["active"] = active

    def _status_now(self, data: Mapping[str, Any]) -> bool:
        state = self.hass.states.get(data.get(A_ENTITY, ""))
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return False
        if state.state in (data.get(A_ACTIVE_STATES) or []):
            return True
        above = data.get(A_ABOVE)
        try:
            return above is not None and float(state.state) > float(above)
        except ValueError:
            return False

    async def _build(self, app: str) -> Screen | render.Rendered:
        now = dt_util.now()
        if app.startswith(APP_PREFIX) and (sub := self.apps.get(app.removeprefix(APP_PREFIX))):
            return await self._build_app(sub.data, sub.title, now)
        if app.startswith("app:"):
            spec = self.settings.custom_apps.get(app.removeprefix("app:"))
            if spec is not None:
                text = self._template(spec.get("text", ""))
                return await self._screen_for(
                    text, spec.get("icon"), spec.get("color"), spec.get("progress"), spec.get("progress_color"),
                    effect=spec.get("effect"),
                )
        return self._clock(now)

    async def _icon(self, spec: str | None, auto: str | None) -> Image.Image | None:
        if not spec or spec == ICON_AUTO:
            return icons.builtin_icon(auto) if auto else None
        if spec == ICON_NONE:
            return None
        return await self.async_icon(spec)

    async def _build_app(self, data: Mapping[str, Any], title: str, now: datetime) -> Screen | render.Rendered:
        kind = data.get(A_TYPE)
        color = render.parse_color(data.get(A_COLOR), self._color())
        effect = data.get(A_EFFECT) or "none"
        lang = self.language
        if kind == T_CLOCK:
            return render.render_clock(
                now, *self.view_size, color, weekdays=WEEKDAYS_SHORT[lang], effect=effect,
                seconds=data.get(A_SECONDS, True), weekday_bar=data.get(A_WEEKDAY_BAR, True),
            )
        icon_spec = data.get(A_ICON)
        if kind == T_DATE:
            cyan = (0, 200, 230)
            if self.tall:
                lines = [Line(WEEKDAYS_SHORT[lang][now.weekday()], color), Line(now.strftime("%d."), cyan),
                         Line(now.strftime("%m."), cyan)]
            elif self.view_size[1] >= 16:
                lines = [Line(WEEKDAYS[lang][now.weekday()], color), Line(now.strftime("%d.%m.%Y"), cyan)]
            else:
                lines = [Line(f"{WEEKDAYS_SHORT[lang][now.weekday()]} {now.strftime('%d.%m.')}", color)]
            return Screen(lines, icon=await self._icon(icon_spec, None), effect=effect)
        if kind == T_WEATHER:
            state = self.hass.states.get(data[A_ENTITY])
            temp = state.attributes.get("temperature")
            text = f"{self._number(temp, 0)}°" if temp is not None else state.state
            icon = await self._icon(icon_spec, icons.WEATHER_ICONS.get(state.state, "cloud"))
            return Screen([Line(text, color)], icon=icon, effect=effect)
        if kind == T_VALUE:
            return await self._value_screen(data, color, effect)
        if kind == T_POWER:
            screen = self._power_screen(data[A_ENTITY])
            if icon_spec and icon_spec != ICON_AUTO:
                screen.icon = await self._icon(icon_spec, None)
            screen.effect = effect
            return screen
        if kind == T_STATUS:
            progress = None
            if (entity := data.get(A_PROGRESS_ENTITY)) and self._usable(entity):
                with contextlib.suppress(ValueError):
                    progress = float(self.hass.states.get(entity).state)
            return await self._screen_for(self._template(data.get(A_TEXT) or title), icon_spec,
                                          data.get(A_COLOR), progress, default_icon="info", effect=effect)
        if kind == T_TEXT:
            return await self._screen_for(self._template(data.get(A_TEXT, "")), icon_spec, data.get(A_COLOR),
                                          effect=effect)
        if kind == T_CALENDAR:
            screen = await self._calendar_screen(data, now, color)
            if icon_spec and icon_spec != ICON_AUTO:
                screen.icon = await self._icon(icon_spec, None)
            screen.effect = effect
            return screen
        return self._clock(now)

    async def _value_screen(self, data: Mapping[str, Any], color: render.RGB, effect: str) -> Screen:
        state = self.hass.states.get(data[A_ENTITY])
        unit = data.get(A_UNIT) or state.attributes.get("unit_of_measurement") or ""
        decimals = data.get(A_DECIMALS)
        value = self._number(state.state, None if decimals is None else int(decimals))
        text = f"{value}{'' if unit in ('%', '°C', '°F', '°', '') else ' '}{unit}"
        if label := data.get(A_LABEL):
            text = f"{label} {text}"
        progress = None
        if data.get(A_PROGRESS):
            lo, hi = float(data.get(A_MIN, 0)), float(data.get(A_MAX, 100))
            with contextlib.suppress(ValueError, ZeroDivisionError):
                progress = (float(state.state) - lo) / (hi - lo) * 100
        auto = icons.DEVICE_CLASS_ICONS.get(state.attributes.get("device_class", ""), "info")
        return Screen([Line(text, color)], icon=await self._icon(data.get(A_ICON), auto), progress=progress,
                      effect=effect)

    @property
    def view_size(self) -> tuple[int, int]:
        """Drawing size: the panel size, width and height swapped when it hangs in portrait."""
        return render.view_size(self.width, self.height, self.settings.orientation)

    @property
    def tall(self) -> bool:
        width, height = self.view_size
        return height > width

    def _clock(self, now: datetime) -> render.Rendered:
        return render.render_clock(now, *self.view_size, self._color(), weekdays=WEEKDAYS_SHORT[self.language],
                                   seconds=True)

    def _template(self, text: str) -> str:
        if "{" not in text:
            return text
        try:
            return str(Template(text, self.hass).async_render(parse_result=False))
        except Exception as err:  # noqa: BLE001 - show the raw text instead of failing the loop
            _LOGGER.warning("%s: template error in %r: %s", self.name, text, err)
            return text

    def _number(self, value: Any, decimals: int | None = None) -> str:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return str(value)
        if decimals is None:
            decimals = 0 if number.is_integer() or abs(number) >= 100 else 1
        text = f"{number:.{decimals}f}"
        return text.replace(".", ",") if self.language == "de" else text

    def _power_screen(self, entity_id: str) -> Screen:
        state = self.hass.states.get(entity_id)
        unit = state.attributes.get("unit_of_measurement", "W")
        try:
            watts = float(state.state) * (1000 if unit == "kW" else 1)
        except ValueError:
            return Screen([Line(state.state)], icon=icons.builtin_icon("power"))
        text = f"{self._number(watts / 1000, 1)} kW" if abs(watts) >= 1000 else f"{self._number(watts, 0)} W"
        if watts < 0:
            color, icon = (0, 200, 60), "solar"  # feeding in
        elif watts < 1000:
            color, icon = (255, 255, 255), "power"
        elif watts < 3000:
            color, icon = (255, 190, 0), "power"
        else:
            color, icon = (255, 40, 20), "power"
        return Screen([Line(text, color)], icon=icons.builtin_icon(icon))

    # ---- calendar ----------------------------------------------------------------------------

    @staticmethod
    def _calendar_key(data: Mapping[str, Any]) -> tuple[tuple[str, ...], int]:
        return tuple(data.get(A_CALENDARS) or []), int(data.get(A_DAYS, DEFAULT_CALENDAR_DAYS))

    async def _refresh_calendars(self) -> None:
        keys = {self._calendar_key(sub.data) for sub in self.apps.values() if sub.data.get(A_TYPE) == T_CALENDAR}
        now = dt_util.utcnow()
        for key in keys:
            calendars, days = key
            fetched, _ = self._calendar_cache.get(key, (None, []))
            if not calendars or (fetched is not None and now - fetched < CALENDAR_REFRESH):
                continue
            try:
                result = await self.hass.services.async_call(
                    "calendar", "get_events",
                    {"entity_id": list(calendars), "duration": {"days": days}},
                    blocking=True, return_response=True,
                )
            except HomeAssistantError as err:
                _LOGGER.warning("%s: reading calendars failed: %s", self.name, err)
                self._calendar_cache[key] = (now, [])
                continue
            events = [ev for cal in (result or {}).values() for ev in cal.get("events", [])]
            for ev in events:
                ev["_start"] = _event_time(ev["start"])
                ev["_end"] = _event_time(ev["end"])
            self._calendar_cache[key] = (now, sorted(events, key=lambda ev: ev["_start"]))

    def _next_event(self, data: Mapping[str, Any]) -> dict[str, Any] | None:
        now = dt_util.now()
        _, events = self._calendar_cache.get(self._calendar_key(data), (None, []))
        for ev in events:
            if ev["_end"] > now:
                return ev
        return None

    async def _calendar_screen(self, data: Mapping[str, Any], now: datetime, color: render.RGB) -> Screen:
        ev = self._next_event(data)
        icon = icons.builtin_icon("calendar")
        if ev is None:
            return Screen([Line("–", color)], icon=icon)
        lang = self.language
        start: datetime = ev["_start"]
        all_day = "T" not in ev["start"]
        days = (start.date() - now.date()).days
        if days <= 0:
            when = TODAY[lang] if all_day or start <= now else start.strftime("%H:%M")
        elif days == 1:
            when = TOMORROW[lang] + ("" if all_day else start.strftime(" %H:%M"))
        else:
            when = WEEKDAYS_SHORT[lang][start.weekday()] + (start.strftime(" %d.%m.") if all_day else start.strftime(" %H:%M"))
        summary = ev.get("summary") or ""
        if self.view_size[1] >= 16:
            return Screen([Line(when, (255, 190, 0)), Line(summary, color)], icon=icon)
        return Screen([Line(f"{when} {summary}", color)], icon=icon)

    # ---- icons ------------------------------------------------------------------------------

    async def _screen_for(self, text: str, icon: str | None, color: Any, progress: Any = None,
                          progress_color: Any = None, default_icon: str | None = None,
                          effect: str | None = None) -> Screen:
        if not icon or icon == ICON_AUTO:
            img = icons.builtin_icon(default_icon) if default_icon else None
        else:
            img = None if icon == ICON_NONE else await self.async_icon(icon)
        lines = [Line(t, render.parse_color(color, self._color())) for t in str(text).split("\n")]
        return Screen(
            lines,
            icon=img,
            progress=float(progress) if progress not in (None, "") else None,
            progress_color=render.parse_color(progress_color, (0, 200, 60)),
            effect=effect or "none",
        )

    async def async_icon(self, spec: str) -> Image.Image | None:
        """Built-in icon name, LaMetric icon id (cached) or an image file in an allowed folder."""
        spec = str(spec).strip()
        if spec in self._icons:
            return self._icons[spec]
        img = icons.builtin_icon(spec)
        if img is None:
            try:
                if spec.isdigit():
                    img = await self._lametric_icon(spec)
                elif self.hass.config.is_allowed_path(spec):
                    data = await self.hass.async_add_executor_job(Path(spec).read_bytes)
                    img = icons.icon_from_bytes(data)
                else:
                    _LOGGER.warning("%s: unknown icon %r (built-in: %s)", self.name, spec, ", ".join(icons.BUILTIN_NAMES))
            except (OSError, ValueError) as err:
                _LOGGER.warning("%s: icon %r not loaded: %s", self.name, spec, err)
        self._icons[spec] = img
        return img

    async def _lametric_icon(self, icon_id: str) -> Image.Image:
        path = self._icon_dir / icon_id
        if not await self.hass.async_add_executor_job(path.exists):
            session = async_get_clientsession(self.hass)
            async with session.get(icons.lametric_url(icon_id), timeout=10) as resp:
                resp.raise_for_status()
                data = await resp.read()

            def _write() -> None:
                self._icon_dir.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)

            await self.hass.async_add_executor_job(_write)
        data = await self.hass.async_add_executor_job(path.read_bytes)
        return icons.icon_from_bytes(data)

    # ---- actions from entities and services -------------------------------------------------

    async def _command(self, data: bytes) -> None:
        try:
            await self.client.async_command(self._ble_device(), data)
        except BLE_ERRORS as err:
            raise HomeAssistantError(f"{self.name}: {err}") from err

    async def async_set_power(self, on: bool) -> None:
        self.settings.power = on
        await self._save()
        await self._command(proto.set_power(on))
        if on:
            self._shown = None
            self._native_clock_shown = False
        self.async_update_listeners()
        self.wake()

    async def async_set_brightness(self, level: int) -> None:
        self.settings.brightness = level
        await self._save()
        await self._command(proto.set_brightness(level))
        self.async_update_listeners()

    async def async_set_settings(self, **changes: Any) -> None:
        for key, value in changes.items():
            setattr(self.settings, key, value)
        await self._save()
        if {"mode", "clock_style", "orientation"} & changes.keys():
            self._native_clock_shown = False
            self._shown = None
        if "app_seconds" in changes:
            self._app_until = 0
        self.async_update_listeners()
        self.wake()

    def next_app(self) -> None:
        self._advance = True
        self.wake()

    def notify(self, note: Notification) -> None:
        self._notifications.append(note)
        self.data.notifications = len(self._notifications)
        self.async_update_listeners()
        self.wake()

    def dismiss(self) -> None:
        self._dismiss = True
        self.wake()

    async def async_set_app(self, name: str, spec: dict[str, Any], lifetime: float | None) -> None:
        if lifetime:
            spec["expires"] = (dt_util.utcnow() + timedelta(seconds=lifetime)).isoformat()
        self.settings.custom_apps[name] = spec
        new = name not in self.settings.known_apps
        if new:
            self.settings.known_apps.append(name)
        await self._save()
        if new and self.on_new_app is not None:
            self.on_new_app(name)
        self.async_update_listeners()
        if self.data.current_app == f"app:{name}":
            self.wake()

    async def async_show_app(self, name: str, show: bool) -> None:
        """Switch a custom page on or off for this panel (the automation keeps updating it)."""
        hidden = set(self.settings.hidden_apps)
        if show:
            hidden.discard(name)
        else:
            hidden.add(name)
        self.settings.hidden_apps = sorted(hidden)
        await self._save()
        self.async_update_listeners()
        if not show and self.data.current_app == f"app:{name}":
            self.next_app()

    async def async_remove_app(self, name: str) -> None:
        if self.settings.custom_apps.pop(name, None) is not None:
            await self._save()
            self.async_update_listeners()
            self.wake()


def _event_time(value: str) -> datetime:
    """Calendar start/end: ISO date (all-day, local midnight) or datetime."""
    if "T" in value:
        parsed = dt_util.parse_datetime(value)
        return dt_util.as_local(parsed)
    day = dt_util.parse_date(value)
    return dt_util.start_of_local_day(day)
