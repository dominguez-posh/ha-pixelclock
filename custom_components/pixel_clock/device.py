"""BLE access to one panel over a persistent connection."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime

from bleak.backends.device import BLEDevice
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

from . import protocol as proto

_LOGGER = logging.getLogger(__name__)

ACK_TIMEOUT = 8.0
COMMAND_ACK_TIMEOUT = 3.0
INFO_TIMEOUT = 5.0
FAST_CHUNK_PAUSE = 0.008  # s between writes without response (~0.2 s per 12 KB window)


class PixelClockClient:
    """Keeps one connection open; serialises commands and waits for the panel's ACKs."""

    def __init__(self, name: str, now: Callable[[], datetime]) -> None:
        self._name = name
        self._now = now  # local wall-clock time of Home Assistant
        self._lock = asyncio.Lock()
        self._client: BleakClientWithServiceCache | None = None
        self._ack: asyncio.Queue[int] = asyncio.Queue()
        self._info: asyncio.Future[bytes] | None = None
        self.device_info: proto.DeviceInfo | None = None
        self.fast_writes = True

    @property
    def connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    @property
    def mtu(self) -> int | None:
        return self._client.mtu_size if self.connected else None

    def _on_disconnect(self, _client: BleakClientWithServiceCache) -> None:
        _LOGGER.debug("%s: disconnected", self._name)
        self._client = None

    def _on_notify(self, _sender: object, data: bytearray) -> None:
        data = bytes(data)
        _LOGGER.debug("%s: notify %s", self._name, data.hex(" "))
        status = proto.ack_status(data)
        if status is not None:
            self._ack.put_nowait(status)
        elif self._info is not None and not self._info.done():
            self._info.set_result(data)

    async def _ensure_connected(self, ble_device: BLEDevice | None) -> BleakClientWithServiceCache:
        if self.connected:
            return self._client
        if ble_device is None:
            raise ConnectionError(f"{self._name} is not in range of a connectable Bluetooth adapter")
        client = await establish_connection(
            BleakClientWithServiceCache, ble_device, self._name,
            disconnected_callback=self._on_disconnect, max_attempts=3,
        )
        try:
            await client.start_notify(proto.NOTIFY_UUID, self._on_notify)
        except Exception:
            await client.disconnect()
            raise
        # BlueZ reports the default MTU (23) until it is acquired; the panel supports 517
        backend = getattr(client, "_backend", None)
        if (acquire := getattr(backend, "_acquire_mtu", None)) is not None:
            try:
                await acquire()
            except Exception as err:  # noqa: BLE001 - small writes still work
                _LOGGER.debug("%s: MTU not acquired: %s", self._name, err)
        self._client = client
        _LOGGER.debug("%s: connected, MTU %s", self._name, client.mtu_size)
        # The time command also returns the device info (panel type and size).
        await self._sync_time(client, self._now())
        return client

    def _drain_acks(self) -> None:
        while not self._ack.empty():
            self._ack.get_nowait()

    async def _wait_ack(self, timeout: float, want: tuple[int, ...]) -> bool:
        loop = asyncio.get_running_loop()
        end = loop.time() + timeout
        while (left := end - loop.time()) > 0:
            try:
                status = await asyncio.wait_for(self._ack.get(), left)
            except TimeoutError:
                return False
            if status in want:
                return True
        return False

    async def _write(self, client: BleakClientWithServiceCache, data: bytes, fast: bool = False) -> None:
        """fast: write without response (measured 10x faster); the panel's window ACK is the check."""
        size = max(20, min(proto.MAX_CHUNK, client.mtu_size - 3))
        for chunk in proto.chunks(data, size):
            await client.write_gatt_char(proto.WRITE_UUID, chunk, response=not fast)
            if fast:
                # without the pause BlueZ on the Pi pushed a 12 KB window faster than the panel takes it
                await asyncio.sleep(FAST_CHUNK_PAUSE)

    async def _command(self, client: BleakClientWithServiceCache, data: bytes) -> None:
        self._drain_acks()
        _LOGGER.debug("%s: write %s", self._name, data.hex(" "))
        await self._write(client, data)
        if not await self._wait_ack(COMMAND_ACK_TIMEOUT, proto.ACK_WINDOW + (proto.ACK_DONE,)):
            _LOGGER.debug("%s: no ACK for %s", self._name, data[:4].hex(" "))

    async def _sync_time(self, client: BleakClientWithServiceCache, now: datetime) -> None:
        loop = asyncio.get_running_loop()
        self._info = loop.create_future()
        try:
            self._drain_acks()
            await self._write(client, proto.set_time(now))
            raw = await asyncio.wait_for(self._info, INFO_TIMEOUT)
            self.device_info = proto.parse_device_info(raw)
            _LOGGER.debug("%s: device info %s", self._name, self.device_info)
        except (TimeoutError, ValueError) as err:
            _LOGGER.debug("%s: no device info: %s", self._name, err)
        finally:
            self._info = None

    async def async_command(self, ble_device: BLEDevice | None, data: bytes) -> None:
        async with self._lock:
            await self._command(await self._ensure_connected(ble_device), data)

    async def async_sync_time(self, ble_device: BLEDevice | None) -> None:
        async with self._lock:
            client = await self._ensure_connected(ble_device)
            await self._sync_time(client, self._now())

    async def async_send_image(self, ble_device: BLEDevice | None, data: bytes, is_gif: bool) -> None:
        """Upload a PNG or GIF and show it (not stored on the panel)."""
        async with self._lock:
            client = await self._ensure_connected(ble_device)
            fast = self.fast_writes
            windows = proto.image_windows(data, is_gif)
            self._drain_acks()
            for index, window in enumerate(windows):
                await self._write(client, window, fast)
                if not await self._wait_ack(ACK_TIMEOUT, proto.ACK_WINDOW + (proto.ACK_DONE,)):
                    if fast:
                        # data may have been dropped: use acknowledged writes from now on
                        _LOGGER.warning("%s: no ACK after a fast upload, switching to acknowledged writes", self._name)
                        self.fast_writes = False
                    raise TimeoutError(f"no ACK for image window {index + 1}/{len(windows)}")
            _LOGGER.debug("%s: sent %s bytes (%s, fast=%s)", self._name, len(data), "gif" if is_gif else "png", fast)

    async def async_disconnect(self) -> None:
        async with self._lock:
            if self._client is not None:
                client, self._client = self._client, None
                await client.disconnect()
