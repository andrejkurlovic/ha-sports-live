"""Sports Live — multi-sport Home Assistant integration powered by ESPN data.

Upstream attribution: Bobsilvio/calcio-live (MIT License). This is a heavily
rewritten fork adding sport-agnostic architecture, multi-sport support (soccer,
NFL, rugby), a proper DataUpdateCoordinator, and updated card compatibility.

License: MIT — see LICENSE file.
"""
from __future__ import annotations

from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, CONF_MODE, _LOGGER
from .coordinator import SportsLiveCoordinator

PLATFORMS = ["sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})

    update_interval = timedelta(minutes=entry.options.get("scan_interval", 3))
    coordinator = SportsLiveCoordinator(hass, entry, update_interval)
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
