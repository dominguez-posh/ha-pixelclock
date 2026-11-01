"""Background effects, clock with seconds and the icon set."""

from datetime import datetime

import pytest
from pixel_clock import effects, icons, render
from pixel_clock.render import Line, Screen

W, H = 64, 16


def test_icons_are_8x8():
    for name in icons.BUILTIN_NAMES:
        img = icons.builtin_icon(name)
        assert img.size == (8, 8), name
        assert img.getbbox() is not None, name  # not empty


@pytest.mark.parametrize("effect", [e for e in effects.EFFECTS if e != "none"])
def test_effect_loops_and_stays_small(effect):
    r = render.render_screen(Screen([Line("11°")], icon=icons.builtin_icon("sun"), effect=effect), W, H)
    assert len(r.frames) == effects.FRAMES
    assert not r.scrolls and r.scroll_ms == 0  # a loop does not extend the page time
    data, is_gif = render.encode(r)
    assert is_gif and len(data) < 24_000
    if effects.has_background(effect):
        # the background stays dim so white text stays readable
        background = effects.background(effect, W, H, 5)
        assert max(max(c) for _, c in background.getcolors(4096)) <= 210


def test_effect_with_scrolling_text_uses_fewer_frames():
    plain = render.render_screen(Screen([Line("Waschmaschine ist fertig")]), W, H)
    fx = render.render_screen(Screen([Line("Waschmaschine ist fertig")], effect="matrix"), W, H)
    assert fx.scrolls and len(fx.frames) <= len(plain.frames) // 2 + 1
    assert abs(fx.scroll_ms - plain.scroll_ms) <= 2 * render.SCROLL_FRAME_MS  # same reading speed


def test_clock_with_seconds_counts_to_the_end_of_the_minute():
    r = render.render_clock(datetime(2026, 11, 1, 9, 5, 50), W, H, seconds=True)
    assert len(r.frames) == 20  # 10 s left, 500 ms frames
    assert not r.scrolls
    bar = [r.frames[0].getpixel((x, y)) for x in (60,) for y in (H - 2, H - 1)]
    assert bar[0] == bar[1] != (0, 0, 0)  # two pixel weekday bar (Sunday = last segment)


def test_unknown_effect_is_still():
    r = render.render_screen(Screen([Line("x")], effect="nope"), W, H)
    assert len(r.frames) == 1
