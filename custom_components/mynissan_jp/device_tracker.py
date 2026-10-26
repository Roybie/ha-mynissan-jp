"""Where the car was last reported."""

from __future__ import annotations

from typing import Any

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import MyNissanConfigEntry
from .entity import MyNissanEntity

LOCATION = EntityDescription(key="location", translation_key="location")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MyNissanConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        MyNissanTracker(coordinator, vin, LOCATION) for vin in coordinator.vehicles
    )


class MyNissanTracker(MyNissanEntity, TrackerEntity):
    _attr_source_type = SourceType.GPS

    @property
    def latitude(self) -> float | None:
        return self.status.latitude

    @property
    def longitude(self) -> float | None:
        return self.status.longitude

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        updated = self.status.location_updated
        return {
            "heading": self.status.heading,
            "last_updated": updated.isoformat() if updated else None,
        }
