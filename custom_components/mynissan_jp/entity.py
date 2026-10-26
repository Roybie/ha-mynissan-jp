"""Base entity for a car."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import VehicleStatus
from .const import DOMAIN
from .coordinator import MyNissanCoordinator


class MyNissanEntity(CoordinatorEntity[MyNissanCoordinator]):
    _attr_has_entity_name = True

    def __init__(
        self, coordinator: MyNissanCoordinator, vin: str, description: EntityDescription
    ) -> None:
        super().__init__(coordinator)
        self.vin = vin
        self.entity_description = description
        self._attr_unique_id = f"{vin}_{description.key}"
        vehicle = coordinator.vehicles[vin]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, vin)},
            manufacturer="Nissan",
            model=vehicle.model,
            model_id=vehicle.model_code,
            name=vehicle.name,
            serial_number=vin,
        )

    @property
    def status(self) -> VehicleStatus | None:
        return (self.coordinator.data or {}).get(self.vin)

    @property
    def available(self) -> bool:
        return super().available and self.status is not None
