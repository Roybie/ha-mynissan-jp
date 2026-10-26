"""Polls Nissan for the latest data of every car on the account."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import MyNissanAuthError, MyNissanClient, MyNissanError, Vehicle, VehicleStatus
from .const import DOMAIN, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

type MyNissanConfigEntry = ConfigEntry[MyNissanCoordinator]


class MyNissanCoordinator(DataUpdateCoordinator[dict[str, VehicleStatus]]):
    """Data for all cars, keyed by VIN."""

    config_entry: MyNissanConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: MyNissanConfigEntry, client: MyNissanClient
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self.client = client
        self.vehicles: dict[str, Vehicle] = {}

    async def _async_setup(self) -> None:
        try:
            vehicles = await self.client.async_get_vehicles()
        except MyNissanAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except MyNissanError as err:
            raise UpdateFailed(str(err)) from err
        self.vehicles = {v.vin: v for v in vehicles}

    async def _async_update_data(self) -> dict[str, VehicleStatus]:
        data = {}
        try:
            for vin in self.vehicles:
                data[vin] = await self.client.async_get_status(vin)
        except MyNissanAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except MyNissanError as err:
            raise UpdateFailed(str(err)) from err
        return data
