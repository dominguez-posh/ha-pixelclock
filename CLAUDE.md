# ha-pixelclock

Home Assistant custom integration `pixel_clock` for iPixel Color BLE LED panels (Action
"LED flexible fun screen", 64x16, name `LED_BLE_36A4FDD4`, MAC 23:2F:36:A4:FD:D4).

## State (2026-11-01)

- Protocol verified live from the laptop (`tools/live_test.py`): device info type 131 = 64x16,
  MTU 517, PNG/GIF upload with ACKs works, GIF with partial frames (disposal 1) decodes correctly
  on the panel. ~5-6 KB/s over BLE from the laptop.
- Integration code complete, lint + tests green; NOT yet running in Home Assistant.
- HA: https://smarthome.andom.eu (2026.10.4), token in ~/.ha_token, `tools/ha_ws.py` lives in
  c:/git/ha-devicontrol. SSH to HA not reachable (port 22 closed externally, LAN IP timed out).
  The panel is seen by the Pi's own adapter (E4:5F:01:32:5C:D3, RSSI ~-59).
- Deploy path: GitHub repo + HACS like ha-devicontrol. Push only when the user says so.

## Rules

- Never commit the vendor APK/APKM (in .gitignore) or decompiled app code.
- Decompiling with jadx was blocked by the auto-mode classifier; the protocol came from DEX string
  checks plus pypixelcolor 0.5.0 (MIT) source.
- Pure modules (protocol, font, icons, render) must not import Home Assistant (tests load them
  without HA via tests/conftest.py).
