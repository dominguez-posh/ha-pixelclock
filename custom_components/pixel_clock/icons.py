"""Built-in 8x8 icons and icon loading (built-in name, LaMetric icon id or image file)."""

from __future__ import annotations

from io import BytesIO

from PIL import Image

PALETTE: dict[str, tuple[int, int, int]] = {
    "W": (255, 255, 255),
    "G": (110, 110, 120),  # grey
    "g": (0, 200, 60),  # green
    "R": (230, 20, 20),
    "Y": (255, 190, 0),
    "O": (255, 110, 0),
    "B": (0, 110, 255),
    "C": (0, 200, 230),  # cyan
    "K": (1, 1, 1),  # black that is not transparent
}

_ICONS: dict[str, list[str]] = {
    "calendar": [
        ".R....R.",
        "RRRRRRRR",
        "RRRRRRRR",
        "WWWWWWWW",
        "WGWGWGWW",
        "WWWWWWWW",
        "WGWGWGWW",
        "WWWWWWWW",
    ],
    "power": [
        "....YY..",
        "...YY...",
        "..YY....",
        ".YYYYYY.",
        "....YY..",
        "...YY...",
        "..YY....",
        ".Y......",
    ],
    "sun": [
        "Y..YY..Y",
        ".Y....Y.",
        "..YYYY..",
        "Y.YYYY.Y",
        "Y.YYYY.Y",
        "..YYYY..",
        ".Y....Y.",
        "Y..YY..Y",
    ],
    "moon": [
        "...YYY..",
        "..YY....",
        ".YY.....",
        ".YY.....",
        ".YY.....",
        ".YY.....",
        "..YY....",
        "...YYY..",
    ],
    "cloud": [
        "........",
        "...WW...",
        "..WWWW..",
        ".WWWWWW.",
        "WWWWWWWW",
        "WWWWWWWW",
        ".WWWWWW.",
        "........",
    ],
    "partlycloudy": [
        "Y.Y.....",
        ".YYY....",
        "YYYWW...",
        ".YWWWWW.",
        "WWWWWWWW",
        "WWWWWWWW",
        ".WWWWWW.",
        "........",
    ],
    "rain": [
        "...GG...",
        "..GGGG..",
        ".GGGGGG.",
        "GGGGGGGG",
        ".GGGGGG.",
        "........",
        "B..B..B.",
        ".B..B..B",
    ],
    "snow": [
        "...GG...",
        "..GGGG..",
        ".GGGGGG.",
        "GGGGGGGG",
        ".GGGGGG.",
        "........",
        "W..W..W.",
        ".W..W..W",
    ],
    "thunder": [
        "...GG...",
        "..GGGG..",
        ".GGGGGG.",
        "GGGGGGGG",
        ".GGYGGG.",
        "...YY...",
        "....Y...",
        "...Y....",
    ],
    "fog": [
        "........",
        "GGGGGG..",
        "........",
        "..GGGGGG",
        "........",
        "GGGGGG..",
        "........",
        "..GGGGGG",
    ],
    "wind": [
        "......W.",
        "WWWWWW.W",
        "......W.",
        "........",
        "WWWWW...",
        ".....W..",
        "WWWW..W.",
        ".....W..",
    ],
    "thermometer": [
        "..WWW...",
        "..WRW...",
        "..WRW...",
        "..WRW...",
        "..WRW...",
        ".WRRRW..",
        ".WRRRW..",
        "..WWW...",
    ],
    "drop": [
        "...BB...",
        "...BB...",
        "..BBBB..",
        "..BBBB..",
        ".BBBBBB.",
        ".BBBBBB.",
        "..BBBB..",
        "........",
    ],
    "battery": [
        "..WWWW..",
        ".WWWWWW.",
        ".WK..KW.",
        ".WKggKW.",
        ".WggggW.",
        ".WggggW.",
        ".WggggW.",
        ".WWWWWW.",
    ],
    "house": [
        "...RR...",
        "..RRRR..",
        ".RRRRRR.",
        "RRRRRRRR",
        ".WWWWWW.",
        ".WCWWOW.",
        ".WWWWOW.",
        ".WWWWOW.",
    ],
    "bell": [
        "...YY...",
        "..YYYY..",
        "..YYYY..",
        ".YYYYYY.",
        ".YYYYYY.",
        "YYYYYYYY",
        "........",
        "...YY...",
    ],
    "warning": [
        "...YY...",
        "..YKKY..",
        "..YKKY..",
        ".YYKKYY.",
        ".YYKKYY.",
        "YYYYYYYY",
        "YYYKKYYY",
        "YYYYYYYY",
    ],
    "heart": [
        ".RR..RR.",
        "RRRRRRRR",
        "RRRRRRRR",
        "RRRRRRRR",
        ".RRRRRR.",
        "..RRRR..",
        "...RR...",
        "........",
    ],
    "car": [
        "........",
        "..BBBB..",
        ".BCCCCB.",
        "BBBBBBBB",
        "BBBBBBBB",
        ".KK..KK.",
        ".KK..KK.",
        "........",
    ],
    "door": [
        ".OOOOOO.",
        ".OOOOOO.",
        ".OOOOOO.",
        ".OOOOYO.",
        ".OOOOOO.",
        ".OOOOOO.",
        ".OOOOOO.",
        ".OOOOOO.",
    ],
    "check": [
        "........",
        ".......g",
        "......gg",
        ".....gg.",
        "g...gg..",
        "gg.gg...",
        ".ggg....",
        "..g.....",
    ],
    "info": [
        "..BBBB..",
        ".BBWWBB.",
        "BBBBBBBB",
        "BBBWWBBB",
        "BBBWWBBB",
        "BBBWWBBB",
        ".BBWWBB.",
        "..BBBB..",
    ],
    "trash": [
        "..GGGG..",
        "GGGGGGGG",
        ".G.G.G..",
        ".G.G.G..",
        ".G.G.G..",
        ".G.G.G..",
        ".G.G.G..",
        "..GGG...",
    ],
    "solar": [
        "Y.....Y.",
        ".Y.Y.Y..",
        "...Y....",
        "BBBBBBBB",
        "BWBWBWBB",
        "BBBBBBBB",
        "BWBWBWBB",
        "BBBBBBBB",
    ],
}

# Weather entity condition -> icon
WEATHER_ICONS: dict[str, str] = {
    "clear-night": "moon",
    "cloudy": "cloud",
    "exceptional": "warning",
    "fog": "fog",
    "hail": "snow",
    "lightning": "thunder",
    "lightning-rainy": "thunder",
    "partlycloudy": "partlycloudy",
    "pouring": "rain",
    "rainy": "rain",
    "snowy": "snow",
    "snowy-rainy": "snow",
    "sunny": "sun",
    "windy": "wind",
    "windy-variant": "wind",
}

# Sensor device class -> icon
DEVICE_CLASS_ICONS: dict[str, str] = {
    "temperature": "thermometer",
    "humidity": "drop",
    "moisture": "drop",
    "power": "power",
    "energy": "power",
    "current": "power",
    "voltage": "power",
    "battery": "battery",
    "monetary": "info",
}

BUILTIN_NAMES = tuple(sorted(_ICONS))


def builtin_icon(name: str) -> Image.Image | None:
    rows = _ICONS.get(name)
    if rows is None:
        return None
    img = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
    for y, row in enumerate(rows):
        for x, c in enumerate(row):
            if c in PALETTE:
                img.putpixel((x, y), PALETTE[c] + (255,))
    return img


def icon_from_bytes(data: bytes) -> Image.Image:
    """First frame of an image file as RGBA (LaMetric icons are GIF or PNG)."""
    with Image.open(BytesIO(data)) as img:
        img.seek(0)
        return img.convert("RGBA")


def lametric_url(icon_id: str) -> str:
    return f"https://developer.lametric.com/content/apps/icon_thumbs/{icon_id}"
