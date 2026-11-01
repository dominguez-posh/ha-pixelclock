"""Display loop for one panel: rotates apps, shows notifications, keeps the BLE connection."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.template import Template
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util
from PIL import Image

from . import icons, render
from . import protocol as proto
from .const import (
    APP_CALENDAR,
    APP_CLOCK,
    APP_DATE,
    APP_POWER,
    APP_WEATHER,
    CALENDAR_REFRESH,
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
    DEFAULT_APP_SECONDS,
    DEFAULT_BRIGHTNESS,
    DEFAULT_CALENDAR_DAYS,
    DEFAULT_NOTIFY_SECONDS,
    DOMAIN,
    MODE_APPS,
    MODE_CLOCK,
    RETRY_SECONDS,
    TIME_SYNC_INTERVAL,
    TODAY,
    TOMORROW,
    WEEKDAYS,
    WEEKDAYS_SHORT,
)
from .device import PixelClockClient
from .render import Line, Screen

_LOGGER = logging.getLogger(__name__)

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


@dataclass
class _Settings:
    power: bool = True
    brightness: int = DEFAULT_BRIGHTNESS
    mode: str = MODE_APPS
    clock_style: int = 1
    auto_rotate: bool = True
    app_seconds: int = DEFAULT_APP_SECONDS
    custom_apps: dict[str, dict[str, Any]] = field(default_factory=dict)


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
        self._calendar_events: list[dict[str, Any]] = []
        self._calendar_fetched: datetime | None = None
        self._icons: dict[str, Image.Image | None] = {}
        self._icon_dir = Path(hass.config.path(".storage", f"{DOMAIN}_icons"))

    # ---- lifecycle -------------------------------------------------------------------------

    async def async_start(self) -> None:
        if data := await self._store.async_load():
            known = _Settings.__dataclass_fields__
            self.settings = _Settings(**{k: v for k, v in data.items() if k in known})
        self._task = self.config_entry.async_create_background_task(
            self.hass, self._run(), f"{DOMAIN} display {self.address}"
        )

    async def async_shutdown(self) -> None:
        await super().async_shutdown()
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        await self.client.async_disconnect()

    async def _save(self) -> None:
        await self._store.async_save(self.settings.__dict__)

    def wake(self) -> None:
        self._wake.set()

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
        if self.options.get(CONF_CALENDARS):
            await self._refresh_calendar()

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
            approx = render.render_clock(now, self.width, self.height, self._color())
            self.data.preview = await self.hass.async_add_executor_job(render.preview, approx)
            self.data.preview_updated = dt_util.utcnow()
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
            note.text, note.icon, note.color, note.progress, note.progress_color, default_icon="bell"
        )
        rendered = await self._send(f"notify:{id(note)}", screen)
        seconds = note.duration or max(DEFAULT_NOTIFY_SECONDS, rendered.cycle_ms / 1000)
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

        rendered = await self._send(current, await self._build(current))
        if self._app_until == 0:
            # counted from the end of the upload, which can take seconds for scrolling text
            seconds = max(self.settings.app_seconds, rendered.cycle_ms / 1000)
            self._app_until = time.monotonic() + seconds
        self._publish(current)

        timeout = self._app_until - time.monotonic() if self.settings.auto_rotate else 30
        if current == APP_CLOCK:
            now = dt_util.now()
            timeout = min(timeout, 60 - now.second - now.microsecond / 1e6 + 0.05)
        await self._sleep(min(timeout, 30))

    async def _send(self, key: str, what: Screen | render.Rendered) -> render.Rendered:
        """Render (in the executor) and upload, unless the panel already shows exactly this."""
        rendered, data, is_gif, digest = await self.hass.async_add_executor_job(self._render, what)
        if self._shown is not None and self._shown.key == key and self._shown.digest == digest:
            return rendered
        await self.client.async_send_image(self._ble_device(), data, is_gif)
        self._shown = _Shown(key, digest, rendered.cycle_ms)
        self._native_clock_shown = False
        self.data.preview = await self.hass.async_add_executor_job(render.preview, rendered)
        self.data.preview_updated = dt_util.utcnow()
        return rendered

    def _render(self, what: Screen | render.Rendered) -> tuple[render.Rendered, bytes, bool, str]:
        rendered = what if isinstance(what, render.Rendered) else render.render_screen(what, self.width, self.height)
        data, is_gif = render.encode(rendered)
        return rendered, data, is_gif, hashlib.sha1(data).hexdigest()

    def _publish(self, app: str) -> None:
        self.data.current_app = app
        self.data.notifications = len(self._notifications)
        self.async_set_updated_data(self.data)

    # ---- apps --------------------------------------------------------------------------------

    def _app_names(self) -> list[str]:
        names: list[str] = []
        opts = self.options
        if opts.get(CONF_SHOW_CLOCK, True):
            names.append(APP_CLOCK)
        if opts.get(CONF_SHOW_DATE, True):
            names.append(APP_DATE)
        if self._usable(opts.get(CONF_WEATHER)):
            names.append(APP_WEATHER)
        if self._usable(opts.get(CONF_POWER)):
            names.append(APP_POWER)
        if opts.get(CONF_CALENDARS) and self._next_event():
            names.append(APP_CALENDAR)
        names.extend(f"sensor:{e}" for e in opts.get(CONF_SENSORS, []) if self._usable(e))
        now = dt_util.utcnow()
        for name, app in list(self.settings.custom_apps.items()):
            if (expires := app.get("expires")) and dt_util.parse_datetime(expires) < now:
                del self.settings.custom_apps[name]
                continue
            names.append(f"app:{name}")
        return names or [APP_CLOCK]

    def _usable(self, entity_id: str | None) -> bool:
        if not entity_id:
            return False
        state = self.hass.states.get(entity_id)
        return state is not None and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN)

    @property
    def app_names(self) -> list[str]:
        return self._app_names()

    def _color(self) -> render.RGB:
        return render.parse_color(self.options.get(CONF_COLOR))

    async def _build(self, app: str) -> Screen | render.Rendered:
        now = dt_util.now()
        color = self._color()
        lang = self.language
        if app == APP_CLOCK:
            return render.render_clock(now, self.width, self.height, color)
        if app == APP_DATE:
            if self.height >= 16:
                return Screen([Line(WEEKDAYS[lang][now.weekday()], color), Line(now.strftime("%d.%m.%Y"), (0, 200, 230))])
            return Screen([Line(f"{WEEKDAYS_SHORT[lang][now.weekday()]} {now.strftime('%d.%m.')}", color)])
        if app == APP_WEATHER:
            state = self.hass.states.get(self.options[CONF_WEATHER])
            temp = state.attributes.get("temperature")
            text = f"{self._number(temp, 0)}°" if temp is not None else state.state
            icon = icons.builtin_icon(icons.WEATHER_ICONS.get(state.state, "cloud"))
            return Screen([Line(text, color)], icon=icon)
        if app == APP_POWER:
            return self._power_screen(self.options[CONF_POWER])
        if app == APP_CALENDAR:
            return await self._calendar_screen(now)
        if app.startswith("sensor:"):
            return self._sensor_screen(app.removeprefix("sensor:"))
        if app.startswith("app:"):
            spec = self.settings.custom_apps.get(app.removeprefix("app:"))
            if spec is None:
                return render.render_clock(now, self.width, self.height, color)
            text = self._template(spec.get("text", ""))
            return await self._screen_for(
                text, spec.get("icon"), spec.get("color"), spec.get("progress"), spec.get("progress_color")
            )
        return render.render_clock(now, self.width, self.height, color)

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
        if abs(watts) >= 1000:
            text = f"{self._number(watts / 1000, 1)} kW"
        else:
            text = f"{self._number(watts, 0)} W"
        if watts < 0:
            color, icon = (0, 200, 60), "solar"  # feeding in
        elif watts < 1000:
            color, icon = (255, 255, 255), "power"
        elif watts < 3000:
            color, icon = (255, 190, 0), "power"
        else:
            color, icon = (255, 40, 20), "power"
        return Screen([Line(text, color)], icon=icons.builtin_icon(icon))

    def _sensor_screen(self, entity_id: str) -> Screen:
        state = self.hass.states.get(entity_id)
        unit = state.attributes.get("unit_of_measurement") or ""
        text = f"{self._number(state.state)}{'' if unit in ('%', '°C', '°F', '') else ' '}{unit}"
        icon_name = state.attributes.get("icon", "")
        icon = icons.DEVICE_CLASS_ICONS.get(state.attributes.get("device_class", ""), "house")
        if "solar" in icon_name:
            icon = "solar"
        return Screen([Line(text, self._color())], icon=icons.builtin_icon(icon))

    # ---- calendar ----------------------------------------------------------------------------

    def _calendar_due(self) -> bool:
        return self._calendar_fetched is None or dt_util.utcnow() - self._calendar_fetched > CALENDAR_REFRESH

    async def _refresh_calendar(self) -> None:
        if not self._calendar_due():
            return
        self._calendar_fetched = dt_util.utcnow()
        calendars = self.options.get(CONF_CALENDARS, [])
        days = int(self.options.get(CONF_CALENDAR_DAYS, DEFAULT_CALENDAR_DAYS))
        try:
            result = await self.hass.services.async_call(
                "calendar", "get_events",
                {"entity_id": calendars, "duration": {"days": days}},
                blocking=True, return_response=True,
            )
        except HomeAssistantError as err:
            _LOGGER.warning("%s: reading calendars failed: %s", self.name, err)
            return
        events = [ev for cal in (result or {}).values() for ev in cal.get("events", [])]
        for ev in events:
            ev["_start"] = _event_time(ev["start"])
            ev["_end"] = _event_time(ev["end"])
        self._calendar_events = sorted(events, key=lambda ev: ev["_start"])

    def _next_event(self) -> dict[str, Any] | None:
        now = dt_util.now()
        for ev in self._calendar_events:
            if ev["_end"] > now:
                return ev
        return None

    async def _calendar_screen(self, now: datetime) -> Screen:
        ev = self._next_event()
        icon = icons.builtin_icon("calendar")
        if ev is None:
            return Screen([Line("–", self._color())], icon=icon)
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
        if self.height >= 16:
            return Screen([Line(when, (255, 190, 0)), Line(summary, self._color())], icon=icon)
        return Screen([Line(f"{when} {summary}", self._color())], icon=icon)

    # ---- icons ------------------------------------------------------------------------------

    async def _screen_for(self, text: str, icon: str | None, color: Any, progress: Any = None,
                          progress_color: Any = None, default_icon: str | None = None) -> Screen:
        img = await self.async_icon(icon) if icon else (icons.builtin_icon(default_icon) if default_icon else None)
        lines = [Line(t, render.parse_color(color, self._color())) for t in str(text).split("\n")]
        return Screen(
            lines,
            icon=img,
            progress=float(progress) if progress not in (None, "") else None,
            progress_color=render.parse_color(progress_color, (0, 200, 60)),
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
        if "mode" in changes or "clock_style" in changes:
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
        await self._save()
        if self.data.current_app == f"app:{name}":
            self.wake()

    async def async_remove_app(self, name: str) -> None:
        if self.settings.custom_apps.pop(name, None) is not None:
            await self._save()
            self.wake()


def _event_time(value: str) -> datetime:
    """Calendar start/end: ISO date (all-day, local midnight) or datetime."""
    if "T" in value:
        parsed = dt_util.parse_datetime(value)
        return dt_util.as_local(parsed)
    day = dt_util.parse_date(value)
    return dt_util.start_of_local_day(day)
