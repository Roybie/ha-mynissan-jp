"""Constants for the MyNISSAN Japan integration."""

from datetime import timedelta

DOMAIN = "mynissan_jp"

CONF_REDIRECT_URL = "redirect_url"
CONF_REFRESH_TOKEN = "refresh_token"

# Reads Nissan's cached copy of the car data, which does not wake the car
SCAN_INTERVAL = timedelta(minutes=5)
