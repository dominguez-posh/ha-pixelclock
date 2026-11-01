"""Load the integration's pure modules (protocol, font, render, icons) without Home Assistant."""

import sys
import types
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "pixel_clock"

# A bare package object: relative imports work, __init__.py (Home Assistant code) is not executed.
pkg = types.ModuleType("pixel_clock")
pkg.__path__ = [str(PKG_DIR)]
sys.modules.setdefault("pixel_clock", pkg)
