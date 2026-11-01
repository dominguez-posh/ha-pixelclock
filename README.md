# Pixel Clock for Home Assistant

Turns a cheap **iPixel Color** Bluetooth LED panel into a smart home display, similar to an
AWTRIX / Ulanzi clock: time, date, weather, current power consumption, the next appointment,
any sensor value and your own apps rotate on the panel, notifications interrupt the rotation.

Tested with the "LED flexible fun screen" sold by Action (64×16, Bluetooth name `LED_BLE_…`,
vendor app *iPixels*). Other iPixel Color panels (32×16 … 448×32) use the same protocol.
No cloud, no bridge, no firmware flashing.

## Requirements

- Home Assistant 2025.3 or newer with the Bluetooth integration
- A **connectable** Bluetooth adapter in range: the host's adapter or an
  [ESPHome Bluetooth proxy](https://esphome.io/components/bluetooth_proxy/)

Home Assistant keeps the connection open, so the iPixels app cannot connect at the same time.

## Installation

### HACS

1. **HACS → ⋮ → Custom repositories**, repository `https://github.com/dominguez-posh/ha-pixelclock`,
   type **Integration**.
2. Install **Pixel Clock (iPixel Color)**, restart Home Assistant.
3. The panel shows up under **Settings → Devices & services → Discovered**. Otherwise
   **Add integration → Pixel Clock**.
4. **Configure** (⚙) picks the apps: clock, date, weather entity, power sensor, calendars,
   further sensors and the text colour.

### Manual

Copy `custom_components/pixel_clock` into `config/custom_components` and restart.

## Entities

| Entity | |
|---|---|
| Light | Power and brightness of the panel |
| Image *Preview* | Live picture of what the panel shows (animated while text scrolls) |
| Select *Mode* | *Apps* (rotation rendered by Home Assistant) or *Built-in clock* (the panel's own clock face) |
| Select *Built-in clock face* | Clock face 0–8 for the built-in clock |
| Switch *Rotate apps* | Off: stays on the current app (refreshed every 30 s) |
| Number *App duration* | Seconds per app (scrolling text gets at least one full pass) |
| Button *Next app* / *Dismiss notification* | |
| Text *Message* | Whatever you type is shown as a notification |
| Sensor *Current app* | Attributes: app list, queued notifications, custom apps |

The panel clock is set from Home Assistant on connect and every hour.

## Actions

```yaml
# notification, shown right away
action: pixel_clock.notify
data:
  text: "Waschmaschine fertig"
  icon: bell            # built-in name, LaMetric icon id (e.g. 2867) or an image file
  color: [0, 200, 255]
  duration: 15

# own app in the rotation; the text is a template, rendered every time the app is shown
action: pixel_clock.set_app
data:
  name: pv
  text: "{{ states('sensor.pv_power') | int }} W"
  icon: solar
  progress: 80          # optional bar 0-100 (a number, set it from the automation)
  lifetime: 3600        # removed when not updated for an hour

action: pixel_clock.remove_app
data:
  name: pv
```

A line break in `text` gives two lines (on 16 px high panels). Text that does not fit scrolls.

Built-in icons: battery, bell, calendar, car, check, cloud, door, drop, fog, heart, house, info,
moon, partlycloudy, power, rain, snow, solar, sun, thermometer, thunder, trash, warning, wind.
LaMetric icons (`developer.lametric.com/icons`) are downloaded once and cached.
Image files must be in an allowed folder (e.g. `/config/www/…`).

## How it works

Home Assistant renders every screen itself (Pillow, built-in 5×7 pixel font with umlauts) and
uploads it as PNG, or as GIF for scrolling text and the blinking clock colon. A still image is a
few hundred bytes, a scrolling line 10–25 KB (2–5 s over Bluetooth). Unchanged screens are not
sent again.

Protocol: GATT service `0x00FA`, write `FA02`, notify `FA03`; checked against the iPixels app
3.8.1 and the reverse engineering in [pypixelcolor](https://github.com/lucagoc/pypixelcolor)
(MIT). Details in [`protocol.py`](custom_components/pixel_clock/protocol.py).

## Development

```
python -m venv .venv && .venv/Scripts/pip install pillow pytest bleak
.venv/Scripts/python -m pytest tests
.venv/Scripts/python tools/preview.py out/            # render sample screens to files
.venv/Scripts/python tools/live_test.py ADDRESS clock # talk to a panel from a PC
```
