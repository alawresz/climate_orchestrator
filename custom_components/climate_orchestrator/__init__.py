"""The Climate Orchestrator integration.

Phase 1: the integration sets up a coordinator that resolves each managed
device's area sensors and the home-wide averages, and exposes a whole-home
climate entity plus diagnostic sensors. Control logic arrives in later phases.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .const import CONFIG_ENTRY_VERSION, PLATFORMS
from .coordinator import SmartClimateConfigEntry, SmartClimateCoordinator

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


async def async_migrate_entry(
    hass: HomeAssistant, entry: SmartClimateConfigEntry
) -> bool:
    """Migrate a config entry created by an older (or newer) version.

    The schema is still v1 — every option added so far has been optional with
    a compatible default, which needs no migration. This scaffold exists so
    the first breaking schema change only adds a step here instead of
    wiring. Returning ``False`` for a *newer* major version blocks downgrades
    cleanly instead of mis-reading an unknown schema.
    """
    return not entry.version > CONFIG_ENTRY_VERSION


async def async_setup_entry(
    hass: HomeAssistant, entry: SmartClimateConfigEntry
) -> bool:
    """Set up Climate Orchestrator from a config entry."""
    coordinator = SmartClimateCoordinator(hass, entry)
    await coordinator.async_load_mpc()
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: SmartClimateConfigEntry
) -> bool:
    """Unload a Climate Orchestrator config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.async_shutdown()
    return unload_ok


async def _async_reload_entry(
    hass: HomeAssistant, entry: SmartClimateConfigEntry
) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)
