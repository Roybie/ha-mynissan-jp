"""Diagnostics: the raw data Nissan returned, to help map new fields."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import CONF_REFRESH_TOKEN
from .coordinator import MyNissanConfigEntry

TO_REDACT = {CONF_REFRESH_TOKEN, "gpsLatitude", "gpsLongitude", "vin"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: MyNissanConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    cars = {}
    for n, (vin, vehicle) in enumerate(coordinator.vehicles.items(), 1):
        status = (coordinator.data or {}).get(vin)
        cars[f"car_{n}"] = {
            "model": vehicle.model,
            "model_code": vehicle.model_code,
            "model_year": vehicle.model_year,
            "raw": async_redact_data(status.raw, TO_REDACT) if status else None,
        }
    return {"entry": async_redact_data(dict(entry.data), TO_REDACT), "cars": cars}
