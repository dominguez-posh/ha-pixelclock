# ha-pixelclock

Home Assistant custom integration `pixel_clock` for iPixel Color BLE LED panels (Action
"LED flexible fun screen", 64x16, name `LED_BLE_36A4FDD4`, MAC 23:2F:36:A4:FD:D4).

## State (2026-11-01)

- Protocol verified live from the laptop (`tools/live_test.py`): device info type 131 = 64x16,
  MTU 517, PNG/GIF upload with ACKs works, GIF with partial frames (disposal 1) decodes correctly
  on the panel. ~5-6 KB/s over BLE from the laptop.
- Running in HA since 2026-11-01: public repo dominguez-posh/ha-pixelclock, installed via HACS
  (HACS repo id 1441811331), entry "Pixel Clock FDD4" (01M6BM54E630TSQ5XP3ZB9K76S) on the Pi's
  own adapter. Options: clock, date, weather.forecast_home, power
  sensor.shellypro3em_2cbcbba65a64_total_active_power, calendar.lucas_privat_2.
- Uploads: write without response, 509-byte chunks, MTU must be acquired on BlueZ (else 23).
  Measured: 22 KB GIF in 0.4 s (laptop); notification visible ~2 s after the action in HA.
- Update flow: push -> `hacs/repository/refresh` + `hacs/repository/download` via ha_ws.py ->
  HA restart (ask the user first). HA: https://smarthome.andom.eu (2026.10.4), token in
  ~/.ha_token, `tools/ha_ws.py` in c:/git/ha-devicontrol. SSH to HA not reachable.
- While HA is connected the panel does not advertise: for laptop tests disable the entry
  (`config_entries/disable`) and enable it again afterwards.

- SSH works from the 10.10.52.x Wi-Fi (`ssh -i ~/.ssh/ha_claude root@10.10.52.130`); blueprints
  were copied to /config/blueprints/automation/pixel_clock/ that way (HACS does not install them).
- In HA: 9 example automations `automation.pixel_clock_*` (Tesla battery/charging, dishwasher,
  washing machine, Kehrbert, welcome home, night mode, living room temperature) and the dashboard
  `/pixel-clock` (created by script via lovelace/config/save).
- README images come from `tools/docs_images.py`; Action article: action.com/de-de/p/3226274.

- USB of the panel is power only (2026-11-01: plugged into the laptop with the original cable,
  no new PnP device at all). Control is BLE only.
- Page settings live in the entry options; the device page has switches/selects writing the same
  options (coordinator.async_set_option), the options form keeps keys it does not show.

## Ideas not done yet

- Animated LaMetric icons (only the first frame is used), night dimming, 12 h clock.

## Rules

- Never commit the vendor APK/APKM (in .gitignore) or decompiled app code.
- Decompiling with jadx was blocked by the auto-mode classifier; the protocol came from DEX string
  checks plus pypixelcolor 0.5.0 (MIT) source.
- Pure modules (protocol, font, icons, render) must not import Home Assistant (tests load them
  without HA via tests/conftest.py).
