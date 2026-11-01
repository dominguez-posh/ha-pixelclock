"""Layout and encoding of rendered screens (64x16 panel)."""

from datetime import datetime
from io import BytesIO

from PIL import Image
from pixel_clock import font, icons, render
from pixel_clock.render import Line, Screen

W, H = 64, 16


def lit(img: Image.Image) -> set[tuple[int, int]]:
    return {(x, y) for x in range(img.width) for y in range(img.height) if img.getpixel((x, y)) != (0, 0, 0)}


def test_every_glyph_fits_the_line():
    for ch in font._GLYPHS:
        g = font.glyph(ch)
        assert 1 <= g.width <= 5, ch
        assert len(g.rows) <= font.LINE_HEIGHT, ch


def test_unknown_characters_fall_back():
    assert font.glyph("é").rows == font.glyph("e").rows
    assert font.glyph("☃").rows == font.glyph("?").rows


def test_short_text_is_big_and_still():
    r = render.render_screen(Screen([Line("12°")], icon=icons.builtin_icon("sun")), W, H)
    assert not r.animated
    pixels = lit(r.frames[0])
    text = {p for p in pixels if p[0] > H}
    assert max(y for _, y in text) - min(y for _, y in text) == 13  # 7 rows at scale 2


def test_long_text_scrolls_and_stays_in_text_area():
    r = render.render_screen(Screen([Line("Waschmaschine ist fertig")], icon=icons.builtin_icon("bell")), W, H)
    assert r.animated and r.cycle_ms > 0
    icon_area = {p for p in lit(r.frames[0]) if p[0] < H}
    for frame in r.frames[::10]:
        assert {p for p in lit(frame) if p[0] < H} == icon_area  # text never draws over the icon


def test_two_lines():
    r = render.render_screen(Screen([Line("Heute"), Line("Müll")]), W, H)
    ys = {y for _, y in lit(r.frames[0])}
    assert min(ys) < 7 and max(ys) > 8


def test_clock_blinks_and_marks_weekday():
    r = render.render_clock(datetime(2026, 11, 1, 9, 5), W, H)  # Sunday
    assert len(r.frames) == 2
    on, off = (lit(f) for f in r.frames)
    assert off < on  # only the colon disappears
    bar = [r.frames[0].getpixel((x, H - 1)) for x in range(W)]
    assert bar[-2] == (255, 255, 255) and bar[1] == render.DIM


def test_gif_shares_a_small_palette():
    r = render.render_screen(Screen([Line("Hallo Lucas! Smarthome läuft.")], icon=icons.builtin_icon("house")), W, H)
    data, is_gif = render.encode(r)
    assert is_gif and len(data) < 200 * len(r.frames)
    with Image.open(BytesIO(data)) as img:
        assert img.n_frames == len(r.frames)


def test_parse_color():
    assert render.parse_color("#ff8000") == (255, 128, 0)
    assert render.parse_color([300, -1, 5]) == (255, 0, 5)
    assert render.parse_color("nope", (1, 2, 3)) == (1, 2, 3)
