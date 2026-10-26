"""Binary sensors for plug, charging, locks, openings, climate and warnings."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import VehicleStatus
from .coordinator import MyNissanConfigEntry
from .entity import MyNissanEntity


def _negate(value: bool | None) -> bool | None:
    return None if value is None else not value


@dataclass(frozen=True, kw_only=True)
class MyNissanBinarySensorDescription(BinarySensorEntityDescription):
    value_fn: Callable[[VehicleStatus], bool | None]
    attrs_fn: Callable[[VehicleStatus], dict[str, Any]] | None = None


BINARY_SENSORS = (
    MyNissanBinarySensorDescription(
        key="plugged_in",
        translation_key="plugged_in",
        device_class=BinarySensorDeviceClass.PLUG,
        value_fn=lambda s: s.plugged_in,
    ),
    MyNissanBinarySensorDescription(
        key="charging",
        translation_key="charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        value_fn=lambda s: s.charging,
    ),
    MyNissanBinarySensorDescription(
        # The lock device class is "on" when unlocked
        key="lock",
        translation_key="lock",
        device_class=BinarySensorDeviceClass.LOCK,
        value_fn=lambda s: _negate(s.locked),
    ),
    MyNissanBinarySensorDescription(
        key="doors",
        translation_key="doors",
        device_class=BinarySensorDeviceClass.DOOR,
        value_fn=lambda s: s.doors_open,
    ),
    MyNissanBinarySensorDescription(
        key="hatch",
        translation_key="hatch",
        device_class=BinarySensorDeviceClass.OPENING,
        value_fn=lambda s: s.hatch_open,
    ),
    MyNissanBinarySensorDescription(
        key="hood",
        translation_key="hood",
        device_class=BinarySensorDeviceClass.OPENING,
        value_fn=lambda s: s.hood_open,
    ),
    MyNissanBinarySensorDescription(
        key="climate",
        translation_key="climate",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda s: s.hvac_on,
    ),
    MyNissanBinarySensorDescription(
        key="warnings",
        translation_key="warnings",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda s: None if s.active_warnings is None else bool(s.active_warnings),
        attrs_fn=lambda s: {"active": s.active_warnings or []},
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MyNissanConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        MyNissanBinarySensor(coordinator, vin, description)
        for vin in coordinator.vehicles
        for description in BINARY_SENSORS
    )


class MyNissanBinarySensor(MyNissanEntity, BinarySensorEntity):
    entity_description: MyNissanBinarySensorDescription

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self.status)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self.status)
