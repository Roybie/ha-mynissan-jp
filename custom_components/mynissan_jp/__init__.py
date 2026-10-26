"""MyNISSAN Japan: the 2025+ (ZE2) Nissan Leaf in Home Assistant."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import MyNissanClient
from .const import CONF_REFRESH_TOKEN
from .coordinator import MyNissanConfigEntry, MyNissanCoordinator

PLATFORMS = [Platform.BINARY_SENSOR, Platform.DEVICE_TRACKER, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: MyNissanConfigEntry) -> bool:
    def save_refresh_token(token: str) -> None:
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_REFRESH_TOKEN: token}
        )

    client = MyNissanClient(
        async_get_clientsession(hass), entry.data[CONF_REFRESH_TOKEN], save_refresh_token
    )
    coordinator = MyNissanCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: MyNissanConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
