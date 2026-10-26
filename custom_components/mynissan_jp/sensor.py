"""Sensors for battery, range, charging and odometer."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfEnergy,
    UnitOfLength,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import CHARGE_STATES, VehicleStatus
from .coordinator import MyNissanConfigEntry
from .entity import MyNissanEntity


@dataclass(frozen=True, kw_only=True)
class MyNissanSensorDescription(SensorEntityDescription):
    value_fn: Callable[[VehicleStatus], Any]


SENSORS = (
    MyNissanSensorDescription(
        key="battery_level",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: s.battery_level,
    ),
    MyNissanSensorDescription(
        key="range",
        translation_key="range",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: s.range_km,
    ),
    MyNissanSensorDescription(
        key="available_energy",
        translation_key="available_energy",
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: s.available_energy_kwh,
    ),
    MyNissanSensorDescription(
        key="battery_capacity",
        translation_key="battery_capacity",
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.capacity_kwh,
    ),
    MyNissanSensorDescription(
        key="charge_state",
        translation_key="charge_state",
        device_class=SensorDeviceClass.ENUM,
        options=[*dict.fromkeys(CHARGE_STATES.values()), "unknown"],
        value_fn=lambda s: s.charge_state,
    ),
    MyNissanSensorDescription(
        key="charge_time_remaining",
        translation_key="charge_time_remaining",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        value_fn=lambda s: s.charge_time_remaining_min,
    ),
    MyNissanSensorDescription(
        key="odometer",
        translation_key="odometer",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda s: s.odometer_km,
    ),
    MyNissanSensorDescription(
        key="internal_temperature",
        translation_key="internal_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: s.internal_temperature,
    ),
    MyNissanSensorDescription(
        key="last_updated",
        translation_key="last_updated",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.battery_updated,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MyNissanConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        MyNissanSensor(coordinator, vin, description)
        for vin in coordinator.vehicles
        for description in SENSORS
    )


class MyNissanSensor(MyNissanEntity, SensorEntity):
    entity_description: MyNissanSensorDescription

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.status)
