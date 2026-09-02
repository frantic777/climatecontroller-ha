"""Home Assistant entry point for AC Brain."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import AcApiClient
from .const import CONF_URL
from .coordinator import AcDataUpdateCoordinator, AcRuntimeData


PLATFORMS = ("climate", "switch", "binary_sensor", "sensor")


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up one AC Brain config entry."""

    client = AcApiClient(async_get_clientsession(hass), entry.data[CONF_URL])
    coordinator = AcDataUpdateCoordinator(hass, client)
    await coordinator.async_config_entry_first_refresh()
    if coordinator.data is None or coordinator.data.api_version != 2:
        raise ConfigEntryError("AC Brain API v2 is required")

    entry.runtime_data = AcRuntimeData(client=client, coordinator=coordinator)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload one AC Brain config entry."""

    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        entry.runtime_data = None
    return unloaded
