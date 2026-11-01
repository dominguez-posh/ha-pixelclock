"""Talk to a panel directly from a PC (bleak), using the integration's protocol and renderer.

  .venv/Scripts/python tools/live_test.py ADDRESS info|clock|scroll|scroll-full|power-on|power-off|bright N|native N
"""

import asyncio
import sys
import time
from datetime import datetime
from pathlib import Path

from bleak import BleakClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
import conftest  # noqa: E402,F401  (registers the pixel_clock package)
from pixel_clock import icons, render  # noqa: E402
from pixel_clock import protocol as proto  # noqa: E402
from pixel_clock.render import Line, Screen  # noqa: E402

notes: asyncio.Queue = asyncio.Queue()


def on_notify(_s, data: bytearray) -> None:
    print(f"  <- {bytes(data).hex(' ')}")
    notes.put_nowait(bytes(data))


async def wait_note(timeout=8.0):
    try:
        return await asyncio.wait_for(notes.get(), timeout)
    except TimeoutError:
        print("  (no notification)")
        return None


async def write(client: BleakClient, data: bytes) -> None:
    size = max(20, min(proto.MAX_CHUNK, client.mtu_size - 3))
    for chunk in proto.chunks(data, size):
        await client.write_gatt_char(proto.WRITE_UUID, chunk, response=True)


async def send_image(client, rendered):
    data, is_gif = render.encode(rendered)
    t = time.monotonic()
    wins = proto.image_windows(data, is_gif)
    print(f"  -> {'gif' if is_gif else 'png'} {len(data)} bytes, {len(wins)} window(s), MTU {client.mtu_size}")
    for w in wins:
        await write(client, w)
        await wait_note()
    print(f"  took {time.monotonic() - t:.1f} s")


async def main(address: str, cmd: str, arg: str | None) -> None:
    async with BleakClient(address, timeout=20) as client:
        await client.start_notify(proto.NOTIFY_UUID, on_notify)
        print("connected, MTU", client.mtu_size)
        await write(client, proto.set_time(datetime.now()))
        info = await wait_note()
        if info:
            print("  info:", proto.parse_device_info(info))
        w, h = proto.DEFAULT_SIZE
        if info:
            di = proto.parse_device_info(info)
            w, h = di.width, di.height
        if cmd == "clock":
            await send_image(client, render.render_clock(datetime.now(), w, h))
        elif cmd in ("scroll", "scroll-full"):
            render.GIF_PARTIAL_FRAMES = cmd == "scroll"
            await send_image(client, render.render_screen(
                Screen([Line("Hallo Lucas! Smarthome läuft.", (255, 190, 0))], icon=icons.builtin_icon("house")), w, h))
        elif cmd == "two":
            await send_image(client, render.render_screen(
                Screen([Line("Mo 09:30", (255, 190, 0)), Line("Zahnarzt")], icon=icons.builtin_icon("calendar")), w, h))
        elif cmd == "power-on":
            await write(client, proto.set_power(True))
            await wait_note(3)
        elif cmd == "power-off":
            await write(client, proto.set_power(False))
            await wait_note(3)
        elif cmd == "bright":
            await write(client, proto.set_brightness(int(arg)))
            await wait_note(3)
        elif cmd == "native":
            await write(client, proto.set_clock_mode(int(arg or 1), datetime.now()))
            await wait_note(3)
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None))
