"""Byte layouts compared with the frames the vendor app / pypixelcolor send."""

import binascii
from datetime import datetime

from pixel_clock import protocol as p

NOW = datetime(2026, 11, 1, 14, 37, 5)  # Sunday


def test_simple_commands():
    assert p.set_power(True) == bytes.fromhex("0500070101")
    assert p.set_power(False) == bytes.fromhex("0500070100")
    assert p.set_brightness(50) == bytes.fromhex("0500048032")
    assert p.set_brightness(150) == bytes.fromhex("0500048064")
    assert p.set_time(NOW) == bytes.fromhex("080001800e250500")
    assert p.set_orientation(2) == bytes.fromhex("0500068002")
    assert p.show_slot(3) == bytes.fromhex("07000880010003")


def test_clock_mode():
    # style, 24h, show date, yy, mm, dd, iso weekday
    assert p.set_clock_mode(1, NOW) == bytes.fromhex("0b000601" "010101" "1a0b0107")


def test_image_single_window():
    data = b"\x89PNG" + bytes(100)
    (win,) = p.image_windows(data, is_gif=False)
    crc = (binascii.crc32(data) & 0xFFFFFFFF).to_bytes(4, "little")
    header = bytes([0x02, 0x00, 0x00]) + len(data).to_bytes(4, "little") + crc + bytes([0x00, 0x00])
    assert win == (len(header) + len(data) + 2).to_bytes(2, "little") + header + data


def test_gif_multi_window():
    data = bytes(range(256)) * 100  # 25600 bytes -> 3 windows
    wins = p.image_windows(data, is_gif=True)
    assert len(wins) == 3
    assert [w[4] for w in wins] == [0x00, 0x02, 0x02]  # option byte
    assert all(w[2] == 0x03 for w in wins)
    assert all(w[13:15] == b"\x02\x00" for w in wins)
    assert sum(len(w) - 15 for w in wins) == len(data)
    assert int.from_bytes(wins[0][:2], "little") == len(wins[0])


def test_ack_and_info():
    assert p.ack_status(bytes.fromhex("0500020003")) == 3
    assert p.ack_status(bytes.fromhex("0b00018083")) is None  # device info is not an ACK
    info = p.parse_device_info(bytes.fromhex("0b000180830102030405ff"))
    assert (info.width, info.height) == (64, 16)
    assert p.size_from_manufacturer_data(bytes.fromhex("00720007040083")) == (64, 16)
    assert p.size_from_manufacturer_data(b"") is None
