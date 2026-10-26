"""Setup, entities, token saving, re-login and the config flow."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mynissan_jp.api import InvalidRedirectError, MyNissanAuthError
from custom_components.mynissan_jp.const import CONF_REFRESH_TOKEN, DOMAIN

from .conftest import VIN

EXCHANGE = "custom_components.mynissan_jp.config_flow.async_exchange_redirect"


def entry_for(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, unique_id="account-1", title="Nissan LEAF",
                            data={CONF_REFRESH_TOKEN: "saved-token"})
    entry.add_to_hass(hass)
    return entry


def state_of(hass: HomeAssistant, platform: str, key: str):
    entity_id = er.async_get(hass).async_get_entity_id(platform, DOMAIN, f"{VIN}_{key}")
    assert entity_id, key
    return hass.states.get(entity_id)


async def test_setup_creates_entities(hass: HomeAssistant, mock_client) -> None:
    entry = entry_for(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    assert state_of(hass, "sensor", "battery_level").state == "93"
    assert state_of(hass, "sensor", "range").state == "570"
    assert state_of(hass, "sensor", "available_energy").state == "77.0"
    assert state_of(hass, "sensor", "odometer").state == "14.3"
    assert state_of(hass, "sensor", "charge_state").state == "not_charging"
    assert state_of(hass, "sensor", "internal_temperature").state == "24.0"
    assert state_of(hass, "sensor", "last_updated").state == "2026-10-25T10:46:21+00:00"
    assert state_of(hass, "binary_sensor", "plugged_in").state == "off"
    assert state_of(hass, "binary_sensor", "charging").state == "off"
    assert state_of(hass, "binary_sensor", "lock").state == "off"  # off = locked
    assert state_of(hass, "binary_sensor", "doors").state == "off"
    assert state_of(hass, "binary_sensor", "climate").state == "off"
    warnings = state_of(hass, "binary_sensor", "warnings")
    assert warnings.state == "off" and warnings.attributes["active"] == []
    tracker = state_of(hass, "device_tracker", "location")
    assert tracker.attributes["latitude"] == 35.6812
    assert tracker.attributes["heading"] == 358.0

    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_rotated_token_is_saved(hass: HomeAssistant, mock_client) -> None:
    entry = entry_for(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    mock_client.on_refresh_token("newer-token")
    assert entry.data[CONF_REFRESH_TOKEN] == "newer-token"


async def test_expired_login_starts_reauth(hass: HomeAssistant, mock_client) -> None:
    mock_client.async_get_vehicles.side_effect = MyNissanAuthError("invalid_grant")
    entry = entry_for(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [f["context"]["source"] for f in flows] == ["reauth"]


async def test_config_flow(hass: HomeAssistant, mock_client) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    url = result["description_placeholders"]["url"]
    assert url.startswith("https://id.nissan.io/") and "code_challenge=" in url

    with patch(EXCHANGE, side_effect=InvalidRedirectError):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"redirect_url": "https://example.com"})
    assert result["errors"] == {"base": "invalid_redirect"}
    # A wrong paste keeps the same login link
    assert result["description_placeholders"]["url"] == url

    with patch(EXCHANGE, return_value="first-token"), \
         patch("custom_components.mynissan_jp.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"redirect_url": "ncx://ciam.prd/login?code=x&state=y"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Nissan LEAF"
    # The token after the client's first renewal, not the one from the code
    assert result["data"] == {CONF_REFRESH_TOKEN: "rotated-token"}
    assert result["result"].unique_id == "account-1"


async def test_rejected_code_makes_new_link(hass: HomeAssistant, mock_client) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER})
    url = result["description_placeholders"]["url"]
    with patch(EXCHANGE, side_effect=MyNissanAuthError("invalid_grant")):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"redirect_url": "ncx://ciam.prd/login?code=x&state=y"})
    assert result["errors"] == {"base": "invalid_auth"}
    assert result["description_placeholders"]["url"] != url


async def test_reauth_updates_token(hass: HomeAssistant, mock_client) -> None:
    entry = entry_for(hass)
    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    with patch(EXCHANGE, return_value="first-token"), \
         patch("custom_components.mynissan_jp.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"redirect_url": "ncx://ciam.prd/login?code=x&state=y"})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_REFRESH_TOKEN] == "rotated-token"
