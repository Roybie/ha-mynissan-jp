"""Update interval options."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import probatio

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import config_validation as cv

from custom_components.mynissan_jp.api import parse_status

from .conftest import RAW
from .test_integration import entry_for


async def setup(hass: HomeAssistant):
    entry = entry_for(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry, entry.runtime_data


async def test_options_flow_sets_intervals(hass: HomeAssistant, mock_client) -> None:
    entry, coordinator = await setup(hass)
    assert coordinator.update_interval == timedelta(minutes=5)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    # The frontend must be able to render the form (as its flow view does)
    fields = probatio.to_field_list(
        result["data_schema"], custom_serializer=cv.custom_serializer)
    assert [f["name"] for f in fields] == ["interval", "interval_charging"]
    assert [f["default"] for f in fields] == [5, 2]

    calls = mock_client.async_get_status.call_count
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"interval": 15.0, "interval_charging": 3.0})
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {"interval": 15, "interval_charging": 3}
    # Applied straight away, with a fresh update
    assert coordinator.update_interval == timedelta(minutes=15)
    assert mock_client.async_get_status.call_count > calls


async def test_charging_uses_shorter_interval(hass: HomeAssistant, mock_client) -> None:
    entry, coordinator = await setup(hass)
    charging = replace(parse_status(RAW), charge_state="charging")
    mock_client.async_get_status.return_value = charging
    await coordinator.async_refresh()
    assert coordinator.update_interval == timedelta(minutes=2)

    mock_client.async_get_status.return_value = parse_status(RAW)
    await coordinator.async_refresh()
    assert coordinator.update_interval == timedelta(minutes=5)


async def test_saving_token_does_not_refresh(hass: HomeAssistant, mock_client) -> None:
    entry, coordinator = await setup(hass)
    calls = mock_client.async_get_status.call_count
    mock_client.on_refresh_token("newer-token")
    await hass.async_block_till_done()
    assert mock_client.async_get_status.call_count == calls
