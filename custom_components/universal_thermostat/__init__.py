"""The universal_thermostat component."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

DOMAIN = "universal_thermostat"
PLATFORMS = ["climate"]

CONFIG_SCHEMA = cv.platform_only_config_schema(DOMAIN)

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Universal Thermostat component."""
    _LOGGER.debug("Setting up %s component", DOMAIN)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Universal Thermostat from a config entry."""
    _LOGGER.debug("Setting up %s config entry %s", DOMAIN, entry.entry_id)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Unloading %s config entry %s", DOMAIN, entry.entry_id)
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    _LOGGER.debug("Reloading %s config entry %s", DOMAIN, entry.entry_id)
    await hass.config_entries.async_reload(entry.entry_id)
