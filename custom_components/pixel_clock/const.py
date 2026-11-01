"""Constants for the Pixel Clock integration."""

from datetime import timedelta

DOMAIN = "pixel_clock"

CONF_WIDTH = "width"
CONF_HEIGHT = "height"

# Options (version 1 kept the built-in pages here; migrated to app subentries in version 2)
CONF_SHOW_CLOCK = "show_clock"
CONF_SHOW_DATE = "show_date"
CONF_SHOW_WEATHER = "show_weather"
CONF_SHOW_POWER = "show_power"
CONF_SHOW_CALENDAR = "show_calendar"
CONF_WEATHER = "weather_entity"
CONF_POWER = "power_entity"
CONF_CALENDARS = "calendar_entities"
CONF_SENSORS = "sensor_entities"
CONF_CALENDAR_DAYS = "calendar_days"
CONF_COLOR = "color"  # default text colour (still an option)
CONF_DEFAULT_APPS = "default_apps"  # entry data: initial apps were created

# Apps: one config subentry of type "app" per page on the panel
SUBENTRY_APP = "app"
APP_PREFIX = "sub:"  # app key in the rotation: sub:<subentry id>
T_CLOCK, T_DATE, T_WEATHER, T_VALUE, T_POWER, T_STATUS, T_TEXT, T_CALENDAR = (
    "clock", "date", "weather", "value", "power", "status", "text", "calendar",
)
APP_TYPES = (T_CLOCK, T_DATE, T_WEATHER, T_VALUE, T_POWER, T_STATUS, T_TEXT, T_CALENDAR)
# subentry data keys
A_TYPE = "type"
A_ENABLED = "enabled"
A_ICON = "icon"
A_COLOR = "color"
A_EFFECT = "effect"
A_ENTITY = "entity"
A_SECONDS = "seconds"
A_WEEKDAY_BAR = "weekday_bar"
A_LABEL = "label"
A_UNIT = "unit"
A_DECIMALS = "decimals"
A_PROGRESS = "progress"
A_MIN = "min"
A_MAX = "max"
A_ACTIVE_STATES = "active_states"
A_ABOVE = "above"
A_OFF_DELAY = "off_delay"
A_TEXT = "text"
A_DONE_TEXT = "done_text"
A_PROGRESS_ENTITY = "progress_entity"
A_CALENDARS = "calendars"
A_DAYS = "days"
ICON_AUTO = "auto"
ICON_NONE = "none"

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
