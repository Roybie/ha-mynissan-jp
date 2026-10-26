"""Constants for the MyNISSAN Japan integration."""

DOMAIN = "mynissan_jp"

CONF_REDIRECT_URL = "redirect_url"
CONF_REFRESH_TOKEN = "refresh_token"

# Options, in minutes. Updates read Nissan's cached copy of the car data,
# which does not wake the car.
CONF_INTERVAL = "interval"
CONF_INTERVAL_CHARGING = "interval_charging"
DEFAULT_INTERVAL = 5
DEFAULT_INTERVAL_CHARGING = 2
