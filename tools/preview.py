"""Render sample screens to PNG/GIF files for a visual check (no device needed).

  .venv/Scripts/python tools/preview.py OUT_DIR [WIDTH HEIGHT]
"""

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
import conftest  # noqa: E402,F401  (registers the pixel_clock package)
from pixel_clock import icons, render  # noqa: E402
from pixel_clock.render import Line, Screen  # noqa: E402

out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
w, h = (int(sys.argv[2]), int(sys.argv[3])) if len(sys.argv) > 3 else (64, 16)

samples = {
    "clock": render.render_clock(datetime(2026, 11, 1, 14, 37), w, h),
    "date": render.render_screen(Screen([Line("Sonntag"), Line("01.11.2026", (0, 200, 230))]), w, h),
    "weather": render.render_screen(Screen([Line("12°C")], icon=icons.builtin_icon("partlycloudy")), w, h),
    "power": render.render_screen(Screen([Line("1,2 kW", (255, 190, 0))], icon=icons.builtin_icon("power")), w, h),
    "export": render.render_screen(
        Screen([Line("-3,4 kW", (0, 200, 60))], icon=icons.builtin_icon("solar"), progress=68), w, h),
    "calendar": render.render_screen(
        Screen([Line("Mo 09:30", (255, 190, 0)), Line("Zahnarzt Dr. Müller")], icon=icons.builtin_icon("calendar")),
        w, h),
    "notify": render.render_screen(
        Screen([Line("Waschmaschine ist fertig!")], icon=icons.builtin_icon("bell")), w, h),
    "font": render.render_screen(Screen([Line("AÄBCDEFGHIJKLMNOÖPQRSßTUÜVWXYZ"),
                                         Line("aäbcdefghijklmnoöpqrstuüvwxyz 0123456789 !?%°€:.,-+/")]), w, h),
}
for name, r in samples.items():
    data, ctype = render.preview(r, 10)
    path = out / f"{name}.{'gif' if ctype == 'image/gif' else 'png'}"
    path.write_bytes(data)
    first, _ = render.preview(render.Rendered([r.frames[min(len(r.frames) - 1, len(r.frames) // 3)]]), 10)
    (out / f"{name}_still.png").write_bytes(first)
    raw, is_gif = render.encode(r)
    print(f"{name:9} frames={len(r.frames):3} device bytes={len(raw):6} gif={is_gif}")
