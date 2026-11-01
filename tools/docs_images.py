"""Render the README images (docs/images) with the integration's own renderer.

  .venv/Scripts/python tools/docs_images.py
"""

import sys
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
import conftest  # noqa: E402,F401  (registers the pixel_clock package)
from pixel_clock import icons, render  # noqa: E402
from pixel_clock.render import Line, Rendered, Screen  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "docs" / "images"
W, H = 64, 16
LED = 10  # px per LED
BEZEL = 14
NOW = datetime(2026, 11, 1, 14, 37)
YELLOW, GREEN, CYAN = (255, 190, 0), (0, 200, 60), (0, 200, 230)


def leds(img: Image.Image) -> Image.Image:
    """Round LEDs on a dark board, like the real panel."""
    out = Image.new("RGB", (img.width * LED, img.height * LED), (12, 12, 14))
    draw = ImageDraw.Draw(out)
    for x in range(img.width):
        for y in range(img.height):
            r, g, b = img.getpixel((x, y))
            color = (r, g, b) if (r, g, b) != (0, 0, 0) else (28, 28, 32)
            draw.ellipse([x * LED + 1, y * LED + 1, x * LED + LED - 2, y * LED + LED - 2], fill=color)
    return out


def panel(img: Image.Image) -> Image.Image:
    board = leds(img)
    out = Image.new("RGB", (board.width + 2 * BEZEL, board.height + 2 * BEZEL), (255, 255, 255))
    draw = ImageDraw.Draw(out)
    draw.rounded_rectangle([0, 0, out.width - 1, out.height - 1], radius=BEZEL, fill=(0, 0, 0))
    out.paste(board, (BEZEL, BEZEL))
    return out


def still(r: Rendered, index: int = 0) -> Image.Image:
    return panel(r.frames[index])


def save_gif(r: Rendered, name: str, step: int = 2) -> None:
    frames = [panel(f) for f in r.frames[::step]]
    durations = [d * step for d in r.durations[::step]] if r.animated else [1000]
    frames[0].save(OUT / name, save_all=True, append_images=frames[1:], duration=durations, loop=0, optimize=True)


def grid(images: list[Image.Image], cols: int, gap: int = 24) -> Image.Image:
    rows = -(-len(images) // cols)
    w, h = images[0].size
    out = Image.new("RGB", (cols * w + (cols - 1) * gap, rows * h + (rows - 1) * gap), (255, 255, 255))
    for i, img in enumerate(images):
        out.paste(img, ((i % cols) * (w + gap), (i // cols) * (h + gap)))
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    ic = icons.builtin_icon
    screens = {
        "clock": render.render_clock(NOW, W, H, seconds=True),
        "date": render.render_screen(Screen([Line("Sonntag"), Line("01.11.2026", CYAN)]), W, H),
        "weather": render.render_screen(Screen([Line("11°")], icon=ic("partlycloudy")), W, H),
        "power": render.render_screen(Screen([Line("1,1 kW", YELLOW)], icon=ic("power")), W, H),
        "feed_in": render.render_screen(Screen([Line("-2,4 kW", GREEN)], icon=ic("solar")), W, H),
        "car": render.render_screen(Screen([Line("48%", GREEN)], icon=ic("ev"), progress=48), W, H),
        "dishwasher": render.render_screen(Screen([Line("133 min", CYAN)], icon=ic("dishwasher"), progress=35), W, H),
        "calendar": render.render_screen(Screen([Line("Mo 09:30", YELLOW), Line("Zahnarzt")], icon=ic("calendar")), W, H),
    }
    grid([still(r) for r in screens.values()], cols=2).save(OUT / "apps.png", optimize=True)
    still(screens["clock"]).save(OUT / "clock.png", optimize=True)

    # background effects (one still per effect) and an animated example
    from pixel_clock import effects  # noqa: PLC0415
    fx = [render.render_screen(Screen([Line(name.title())], effect=name), W, H)
          for name in effects.EFFECTS if name != "none"]
    grid([panel(r.frames[len(r.frames) // 3]) for r in fx], cols=2).save(OUT / "effects.png", optimize=True)
    save_gif(render.render_screen(Screen([Line("11°")], icon=ic("snowflake"), effect="snow"), W, H), "effect_snow.gif",
             step=1)
    save_gif(render.render_clock(datetime(2026, 11, 1, 14, 37, 50), W, H, seconds=True), "clock_seconds.gif", step=1)

    notify = render.render_screen(Screen([Line("Waschmaschine fertig!", GREEN)], icon=ic("washer")), W, H)
    save_gif(notify, "notification.gif")
    save_gif(render.render_clock(NOW, W, H), "clock.gif", step=1)

    # portrait: drawn on 16x64, shown upright
    tall = [
        render.render_clock(NOW, H, W, seconds=True),
        render.render_screen(Screen([Line("11°")], icon=ic("cloud")), H, W),
        render.render_screen(Screen([Line("1,1 kW", YELLOW)], icon=ic("power")), H, W),
        render.render_screen(Screen([Line("48%", GREEN)], icon=ic("car"), progress=48), H, W),
    ]
    grid([still(r) for r in tall], cols=4, gap=40).save(OUT / "portrait.png", optimize=True)

    icon_strip = Image.new("RGB", (len(icons.BUILTIN_NAMES) * 9 + 1, 10), (0, 0, 0))
    for i, name in enumerate(icons.BUILTIN_NAMES):
        icon_strip.paste(ic(name), (1 + i * 9, 1), ic(name))
    leds(icon_strip).save(OUT / "icons.png", optimize=True)
    for f in sorted(OUT.iterdir()):
        print(f.name, f.stat().st_size)


if __name__ == "__main__":
    main()
