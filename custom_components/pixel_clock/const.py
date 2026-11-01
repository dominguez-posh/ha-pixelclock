"""Constants for the Pixel Clock integration."""

from datetime import timedelta

DOMAIN = "pixel_clock"

CONF_WIDTH = "width"
CONF_HEIGHT = "height"

# Options: built-in apps
CONF_SHOW_CLOCK = "show_clock"
CONF_SHOW_DATE = "show_date"
CONF_SHOW_WEATHER = "show_weather"
CONF_SHOW_POWER = "show_power"
CONF_SHOW_CALENDAR = "show_calendar"
# page switches on the device page: option key -> translation key of the switch
PAGE_SWITCHES = {
    CONF_SHOW_CLOCK: "page_clock",
    CONF_SHOW_DATE: "page_date",
    CONF_SHOW_WEATHER: "page_weather",
    CONF_SHOW_POWER: "page_power",
    CONF_SHOW_CALENDAR: "page_calendar",
}
CONF_WEATHER = "weather_entity"
CONF_POWER = "power_entity"
CONF_CALENDARS = "calendar_entities"
CONF_SENSORS = "sensor_entities"
CONF_CALENDAR_DAYS = "calendar_days"
CONF_COLOR = "color"

DEFAULT_CALENDAR_DAYS = 3

# Display modes
MODE_APPS = "apps"
MODE_CLOCK = "native_clock"
MODES = (MODE_APPS, MODE_CLOCK)

DEFAULT_APP_SECONDS = 8
MIN_APP_SECONDS = 3
MAX_APP_SECONDS = 120
DEFAULT_NOTIFY_SECONDS = 10
DEFAULT_BRIGHTNESS = 50  # 0-100 on the panel

CALENDAR_REFRESH = timedelta(minutes=5)
TIME_SYNC_INTERVAL = timedelta(hours=1)
RETRY_SECONDS = (5, 10, 30, 60)

# Built-in app names (custom apps must not use them)
APP_CLOCK = "clock"
APP_DATE = "date"
APP_WEATHER = "weather"
APP_POWER = "power"
APP_CALENDAR = "calendar"
BUILTIN_APPS = (APP_CLOCK, APP_DATE, APP_WEATHER, APP_POWER, APP_CALENDAR)

WEEKDAYS = {
    "de": ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"),
    "en": ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"),
}
WEEKDAYS_SHORT = {
    "de": ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"),
    "en": ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"),
}
TODAY = {"de": "Heute", "en": "Today"}
TOMORROW = {"de": "Morgen", "en": "Tmrw"}
