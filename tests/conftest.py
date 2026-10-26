"""Fixtures for the MyNISSAN Japan tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.mynissan_jp.api import Vehicle, parse_status

VIN = "SJNTESTVIN0000001"

# Shapes as returned by the backend for a 2025 Leaf (ZE2), location made up
RAW = {
    "battery": {
        "timestamp": "2026-10-25T10:46:21Z", "batteryLevel": 93, "batteryAutonomy": 570,
        "batteryCapacity": 79, "batteryAvailableEnergy": 77, "plugStatus": 0,
        "chargingStatus": 0.0, "chargingRemainingTime": 0,
    },
    "cockpit": {"fuelAutonomy": 0.0, "totalMileage": 14.3000001907349},
    "hvac": {"lastUpdateTime": "2026-10-25T08:09:06Z", "internalTemperature": 24.0,
             "hvacStatus": "off"},
    "lock": {
        "lastUpdateTime": "2026-10-25T10:47:53Z", "lockStatus": "locked",
        "doorStatusFrontLeft": "closed", "doorStatusFrontRight": "closed",
        "doorStatusRearLeft": "closed", "doorStatusRearRight": "closed",
        "engineHoodStatus": "closed", "hatchStatus": "closed", "sunroofStatus": "invalid",
    },
    "location": {"gpsDirection": 358.0, "gpsLatitude": "35.6812", "gpsLongitude": "139.7671",
                 "lastUpdateTime": "2026-10-25T03:19:29Z"},
    "health": {"malfunctionIndicatorLamps": {"airbagWarning": 0, "oilPressureSwitch": 1}},
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def vehicle() -> Vehicle:
    return Vehicle(vin=VIN, model="LEAF", model_code="ZE2", model_year="2025",
                   nickname=None, image_url=None)


@pytest.fixture
def mock_client(vehicle):
    """Patch the client the integration creates; keeps the token callback."""
    client = MagicMock()
    client.account_id = "account-1"
    client.refresh_token = "rotated-token"
    client.async_get_vehicles = AsyncMock(return_value=[vehicle])
    client.async_get_status = AsyncMock(return_value=parse_status(RAW))

    def factory(session, refresh_token, on_refresh_token=None):
        client.on_refresh_token = on_refresh_token
        return client

    with patch("custom_components.mynissan_jp.MyNissanClient", side_effect=factory), \
         patch("custom_components.mynissan_jp.config_flow.MyNissanClient", side_effect=factory):
        yield client
