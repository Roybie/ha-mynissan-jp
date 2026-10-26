"""Client for the Japanese MyNISSAN backend used by the 2025+ (ZE2) Leaf.

Sign-in goes through NISSAN ID (id.nissan.io) with OAuth + PKCE. Its id_token
is exchanged for a token of the NissanConnect app backend, which serves the
car data. This module does not depend on Home Assistant.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import aiohttp

_LOGGER = logging.getLogger(__name__)

CIAM_BASE = "https://id.nissan.io/9d5118a8-dc9c-4e8f-8924-4781cf369f41/login/"
CLIENT_ID = "4db8eab8-8088-4b92-9c14-9bc89fa49c2a"
REDIRECT_URI = "ncx://ciam.prd/login"
BFF_BASE = "https://nc-app-bff-prod.apps.jp.kamereon.io/nc-app-bff/"
CAR_ADAPTER = BFF_BASE + "alliance/car-adapter/"
APP_ID = "jp.co.nissan.nissanconnect.ncx"

TIMEOUT = aiohttp.ClientTimeout(total=30)
# Renew the backend token this long before it expires
TOKEN_MARGIN = 120

DOORS = (
    "doorStatusFrontLeft",
    "doorStatusFrontRight",
    "doorStatusRearLeft",
    "doorStatusRearRight",
)
# Health-status lamps that are not warnings (the oil pressure switch reads 1
# on a healthy EV)
NOT_WARNINGS = {"oilPressureSwitch", "lampRequest"}

# chargingStatus values, as used across the Alliance (Kamereon) platform
CHARGE_STATES = {
    0.0: "not_charging",
    0.1: "waiting_for_schedule",
    0.2: "charge_ended",
    0.3: "waiting_for_current",
    0.4: "flap_open",
    0.5: "waiting",
    1.0: "charging",
    -1.0: "error",
    -1.1: "unavailable",
}


class MyNissanError(Exception):
    """Any failure talking to the backend."""


class MyNissanAuthError(MyNissanError):
    """The saved login is no longer valid; the user has to sign in again."""


class InvalidRedirectError(MyNissanError):
    """The pasted address is not a login redirect from this attempt."""


@dataclass
class AuthorizeRequest:
    """One browser login attempt (PKCE verifier and state)."""

    verifier: str
    state: str
    url: str

    @classmethod
    def new(cls) -> AuthorizeRequest:
        verifier = secrets.token_urlsafe(64)
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        state = secrets.token_urlsafe(16)
        url = CIAM_BASE + "authorize?" + urlencode(
            {
                "client_id": CLIENT_ID,
                "response_type": "code",
                "redirect_uri": REDIRECT_URI,
                "scope": "openid",
                "state": state,
                "nonce": secrets.token_urlsafe(16),
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "ui_locales": "ja",
            }
        )
        return cls(verifier, state, url)


async def async_exchange_redirect(
    session: aiohttp.ClientSession, auth: AuthorizeRequest, redirect_url: str
) -> str:
    """Turn the pasted ncx://ciam.prd/login?code=... address into a refresh token."""
    query = parse_qs(urlparse(redirect_url.strip()).query)
    if "code" not in query:
        raise InvalidRedirectError("No code in the address")
    if query.get("state", [None])[0] != auth.state:
        raise InvalidRedirectError("The address is from a different login attempt")

    token = await _ciam_token(
        session,
        {
            "grant_type": "authorization_code",
            "client_id": CLIENT_ID,
            "code": query["code"][0],
            "redirect_uri": REDIRECT_URI,
            "code_verifier": auth.verifier,
        },
    )
    return token["refresh_token"]


async def _ciam_token(session: aiohttp.ClientSession, data: dict) -> dict:
    try:
        async with session.post(CIAM_BASE + "token", data=data, timeout=TIMEOUT) as resp:
            body = await resp.json(content_type=None)
            status = resp.status
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
        raise MyNissanError(f"NISSAN ID request failed: {err}") from err

    if status in (400, 401) and isinstance(body, dict) and body.get("error") in (
        "invalid_grant",
        "invalid_token",
        "unauthorized_client",
    ):
        raise MyNissanAuthError(body.get("error_description") or body["error"])
    if status >= 300 or not isinstance(body, dict) or "id_token" not in body:
        raise MyNissanError(f"NISSAN ID answered {status}: {body}")
    return body


@dataclass
class Vehicle:
    """A car on the account."""

    vin: str
    model: str
    model_code: str | None
    model_year: str | None
    nickname: str | None
    image_url: str | None

    @property
    def name(self) -> str:
        return self.nickname or f"Nissan {self.model}"


@dataclass
class VehicleStatus:
    """The latest data Nissan holds for a car (it does not wake the car)."""

    battery_level: int | None = None
    range_km: int | None = None
    available_energy_kwh: float | None = None
    capacity_kwh: float | None = None
    plugged_in: bool | None = None
    charge_state: str | None = None
    charge_time_remaining_min: int | None = None
    battery_updated: datetime | None = None
    odometer_km: float | None = None
    internal_temperature: float | None = None
    hvac_on: bool | None = None
    hvac_updated: datetime | None = None
    locked: bool | None = None
    doors_open: bool | None = None
    hatch_open: bool | None = None
    hood_open: bool | None = None
    lock_updated: datetime | None = None
    latitude: float | None = None
    longitude: float | None = None
    heading: float | None = None
    location_updated: datetime | None = None
    active_warnings: list[str] | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def charging(self) -> bool | None:
        if self.charge_state is None:
            return None
        return self.charge_state == "charging"


def _time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _opening(attrs: dict, *keys: str) -> bool | None:
    """True if any of the openings is open; None if the car reports none of them."""
    states = [attrs.get(k) for k in keys if attrs.get(k) in ("open", "closed")]
    if not states:
        return None
    return "open" in states


class MyNissanClient:
    """An account on the MyNISSAN backend."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        refresh_token: str,
        on_refresh_token: Callable[[str], None] | None = None,
    ) -> None:
        self._session = session
        self.refresh_token = refresh_token
        self._on_refresh_token = on_refresh_token
        self._access_token: str | None = None
        self._expires_at = 0.0
        self._lock = asyncio.Lock()
        self.account_id: str | None = None

    async def _token(self, force: bool = False) -> str:
        async with self._lock:
            if not force and self._access_token and time.monotonic() < self._expires_at:
                return self._access_token

            ciam = await _ciam_token(
                self._session,
                {
                    "grant_type": "refresh_token",
                    "client_id": CLIENT_ID,
                    "refresh_token": self.refresh_token,
                },
            )
            # NISSAN ID hands out a new refresh token every time and the old
            # one stops working, so it has to be saved straight away.
            if ciam.get("refresh_token") and ciam["refresh_token"] != self.refresh_token:
                self.refresh_token = ciam["refresh_token"]
                if self._on_refresh_token:
                    self._on_refresh_token(self.refresh_token)

            status, body = await self._raw(
                "POST",
                BFF_BASE + "nissan/account/v1/exchange-token",
                json={
                    "data": {
                        "type": "exchangeToken",
                        "id": "1",
                        "attributes": {"token": ciam["id_token"]},
                    }
                },
            )
            attrs = _attributes(body)
            if status >= 300 or not attrs.get("access_token"):
                raise MyNissanError(f"Token exchange failed ({status}): {_errors(body)}")
            self._access_token = attrs["access_token"]
            self._expires_at = time.monotonic() + int(attrs.get("expires_in", 3600)) - TOKEN_MARGIN
            self.account_id = attrs.get("ropId") or (body.get("data") or {}).get("id")
            return self._access_token

    async def _raw(self, method: str, url: str, **kwargs) -> tuple[int, Any]:
        headers = {"x-app-id": APP_ID, **kwargs.pop("headers", {})}
        try:
            async with self._session.request(
                method, url, headers=headers, timeout=TIMEOUT, **kwargs
            ) as resp:
                return resp.status, await resp.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
            raise MyNissanError(f"{method} {url.removeprefix(BFF_BASE)} failed: {err}") from err

    async def _get(self, url: str, **kwargs) -> dict:
        """GET with the backend token, signing in again once if it was rejected."""
        for attempt in range(2):
            token = await self._token(force=attempt > 0)
            status, body = await self._raw(
                "GET", url, headers={"Authorization": f"Bearer {token}"}, **kwargs
            )
            if status != 401:
                break
        if status >= 300 or not isinstance(body, (dict, list)) or (
            isinstance(body, dict) and "errors" in body
        ):
            raise MyNissanError(
                f"GET {url.removeprefix(BFF_BASE)} answered {status}: {_errors(body)}"
            )
        return body

    async def async_get_vehicles(self) -> list[Vehicle]:
        info = await self._get(BFF_BASE + "nissan/account/v1/token-info")
        vehicles = []
        for entry in _attributes(info).get("vehicles", []):
            vin = entry["vin"].upper()
            try:
                details = await self._get(BFF_BASE + f"nissan/config/v1/cars/{vin}/details")
            except MyNissanError as err:
                _LOGGER.debug("No details for car ...%s: %s", vin[-3:], err)
                details = {}
            model = details.get("model") or {}
            vehicles.append(
                Vehicle(
                    vin=vin,
                    model=model.get("displayModelName") or "LEAF",
                    model_code=model.get("code"),
                    model_year=model.get("year"),
                    nickname=details.get("nickname"),
                    image_url=details.get("vehicleImageUrl"),
                )
            )
        return vehicles

    async def async_get_status(self, vin: str) -> VehicleStatus:
        """Read everything Nissan holds for the car. Only the battery is required."""
        paths = {
            "battery": f"v2/cars/{vin}/battery-status",
            "cockpit": f"v2/cars/{vin}/cockpit",
            "hvac": f"v1/cars/{vin}/hvac-status",
            "lock": f"v1/cars/{vin}/lock-status",
            "location": f"v1/cars/{vin}/location",
            "health": f"v1/cars/{vin}/health-status",
        }
        results = await asyncio.gather(
            *(self._get(CAR_ADAPTER + path) for path in paths.values()),
            return_exceptions=True,
        )
        raw: dict[str, dict] = {}
        for name, result in zip(paths, results):
            if isinstance(result, MyNissanAuthError):
                raise result
            if isinstance(result, BaseException):
                if name == "battery":
                    raise result
                _LOGGER.debug("%s unavailable for car ...%s: %s", name, vin[-3:], result)
                continue
            raw[name] = _attributes(result)
        return parse_status(raw)


def parse_status(raw: dict[str, dict]) -> VehicleStatus:
    status = VehicleStatus(raw=raw)

    if battery := raw.get("battery"):
        status.battery_level = battery.get("batteryLevel")
        status.range_km = battery.get("batteryAutonomy")
        status.available_energy_kwh = _float(battery.get("batteryAvailableEnergy"))
        status.capacity_kwh = _float(battery.get("batteryCapacity"))
        if battery.get("plugStatus") in (0, 1):
            status.plugged_in = battery["plugStatus"] == 1
        charging = _float(battery.get("chargingStatus"))
        if charging is not None:
            status.charge_state = CHARGE_STATES.get(round(charging, 1), "unknown")
        status.charge_time_remaining_min = battery.get("chargingRemainingTime")
        status.battery_updated = _time(battery.get("timestamp"))

    if cockpit := raw.get("cockpit"):
        status.odometer_km = _float(cockpit.get("totalMileage"))
        if status.odometer_km is not None:
            status.odometer_km = round(status.odometer_km, 1)

    if hvac := raw.get("hvac"):
        status.internal_temperature = _float(hvac.get("internalTemperature"))
        if hvac.get("hvacStatus") in ("on", "off"):
            status.hvac_on = hvac["hvacStatus"] == "on"
        status.hvac_updated = _time(hvac.get("lastUpdateTime"))

    if lock := raw.get("lock"):
        if lock.get("lockStatus") in ("locked", "unlocked"):
            status.locked = lock["lockStatus"] == "locked"
        status.doors_open = _opening(lock, *DOORS)
        status.hatch_open = _opening(lock, "hatchStatus")
        status.hood_open = _opening(lock, "engineHoodStatus")
        status.lock_updated = _time(lock.get("lastUpdateTime"))

    if location := raw.get("location"):
        status.latitude = _float(location.get("gpsLatitude"))
        status.longitude = _float(location.get("gpsLongitude"))
        status.heading = _float(location.get("gpsDirection"))
        status.location_updated = _time(location.get("lastUpdateTime"))

    if health := raw.get("health"):
        lamps = health.get("malfunctionIndicatorLamps") or {}
        status.active_warnings = sorted(
            name for name, value in lamps.items() if value and name not in NOT_WARNINGS
        )

    return status


def _attributes(body: Any) -> dict:
    if isinstance(body, dict):
        return (body.get("data") or {}).get("attributes") or {}
    return {}


def _errors(body: Any) -> Any:
    if isinstance(body, dict) and "errors" in body:
        return [f"{e.get('code')} {e.get('detail')}" for e in body["errors"]]
    return body
