"""Config flow for AC Brain."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import AcApiClient, AcApiError
from .const import CONF_URL, DEFAULT_URL, DOMAIN


class KotlinAcConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configure or move an AC Brain controller."""

    # The persisted schema remains {"url": str}, so existing entries need no
    # migration despite the integration implementation version changing.
    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ):
        """Handle initial setup."""

        # The entities intentionally keep their historical constant unique IDs.
        # Limit the integration to one controller so those IDs can never collide.
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        errors: dict[str, str] = {}
        suggested_url = (
            user_input.get(CONF_URL, DEFAULT_URL)
            if user_input is not None
            else DEFAULT_URL
        )

        if user_input is not None:
            try:
                client = self._client(user_input[CONF_URL])
            except (KeyError, TypeError, ValueError):
                errors["base"] = "invalid_url"
            else:
                try:
                    state = await client.async_get_state()
                except AcApiError:
                    errors["base"] = "cannot_connect"
                else:
                    if state.api_version != 2:
                        errors["base"] = "unsupported_api_version"
                    else:
                        normalized_url = client.base_url
                        await self.async_set_unique_id(normalized_url)
                        self._abort_if_unique_id_configured()
                        return self.async_create_entry(
                            title="AC Brain",
                            data={CONF_URL: normalized_url},
                        )

        return self._show_form("user", suggested_url, errors)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ):
        """Validate and update the controller URL for an existing entry."""

        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        suggested_url = (
            user_input.get(CONF_URL, entry.data[CONF_URL])
            if user_input is not None
            else entry.data[CONF_URL]
        )

        if user_input is not None:
            try:
                client = self._client(user_input[CONF_URL])
            except (KeyError, TypeError, ValueError):
                errors["base"] = "invalid_url"
            else:
                normalized_url = client.base_url
                if self._url_is_configured(
                    normalized_url, excluding_entry_id=entry.entry_id
                ):
                    errors["base"] = "already_configured"
                else:
                    try:
                        state = await client.async_get_state()
                    except AcApiError:
                        errors["base"] = "cannot_connect"
                    else:
                        if state.api_version != 2:
                            errors["base"] = "unsupported_api_version"
                        else:
                            # The entry's identity and entity history survive a
                            # move to a new controller address.
                            if entry.unique_id is not None:
                                await self.async_set_unique_id(entry.unique_id)
                                self._abort_if_unique_id_mismatch()
                            return self.async_update_reload_and_abort(
                                entry,
                                data_updates={CONF_URL: normalized_url},
                                reload_even_if_entry_is_unchanged=False,
                            )

        return self._show_form("reconfigure", suggested_url, errors)

    def _client(self, raw_url: str) -> AcApiClient:
        return AcApiClient(async_get_clientsession(self.hass), raw_url)

    def _url_is_configured(
        self, normalized_url: str, *, excluding_entry_id: str | None = None
    ) -> bool:
        """Compare normalized entry URLs, including older trailing-slash entries."""

        for entry in self._async_current_entries():
            if entry.entry_id == excluding_entry_id:
                continue
            raw_url = entry.data.get(CONF_URL)
            try:
                existing_url = self._client(raw_url).base_url
            except (TypeError, ValueError):
                continue
            if existing_url == normalized_url:
                return True
        return False

    def _show_form(
        self, step_id: str, suggested_url: str, errors: dict[str, str]
    ):
        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema(
                {vol.Required(CONF_URL, default=suggested_url): str}
            ),
            errors=errors,
        )
