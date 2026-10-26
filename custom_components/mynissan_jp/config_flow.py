"""Sign in with a NISSAN ID.

NISSAN ID only lets the MyNISSAN app's own address (ncx://...) receive the
login, so the user signs in in their browser and pastes that address back.
"""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import SOURCE_REAUTH, ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    AuthorizeRequest,
    InvalidRedirectError,
    MyNissanAuthError,
    MyNissanClient,
    MyNissanError,
    async_exchange_redirect,
)
from .const import CONF_REDIRECT_URL, CONF_REFRESH_TOKEN, DOMAIN

_LOGGER = logging.getLogger(__name__)

SCHEMA = vol.Schema({vol.Required(CONF_REDIRECT_URL): str})


class MyNissanConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._auth = AuthorizeRequest.new()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self._async_login("user", user_input)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self._async_login("reauth_confirm", user_input)

    async def _async_login(
        self, step_id: str, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            session = async_get_clientsession(self.hass)
            try:
                refresh_token = await async_exchange_redirect(
                    session, self._auth, user_input[CONF_REDIRECT_URL]
                )
                client = MyNissanClient(session, refresh_token)
                vehicles = await client.async_get_vehicles()
            except InvalidRedirectError:
                errors["base"] = "invalid_redirect"
            except MyNissanAuthError:
                errors["base"] = "invalid_auth"
            except MyNissanError:
                _LOGGER.exception("Could not sign in to MyNISSAN")
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(client.account_id)
                # The client renews the token on first use, so take its copy
                data = {CONF_REFRESH_TOKEN: client.refresh_token}
                if self.source == SOURCE_REAUTH:
                    self._abort_if_unique_id_mismatch()
                    return self.async_update_reload_and_abort(
                        self._get_reauth_entry(), data_updates=data
                    )
                self._abort_if_unique_id_configured()
                title = vehicles[0].name if len(vehicles) == 1 else "MyNISSAN"
                return self.async_create_entry(title=title, data=data)

            # A login code works only once, so start a new attempt
            if errors["base"] != "invalid_redirect":
                self._auth = AuthorizeRequest.new()

        return self.async_show_form(
            step_id=step_id,
            data_schema=SCHEMA,
            description_placeholders={"url": self._auth.url},
            errors=errors,
        )
