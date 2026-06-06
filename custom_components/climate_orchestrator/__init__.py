"""The Climate Orchestrator integration.

Entry setup wires a coordinator that resolves each managed device's area
sensors and the home-wide averages and runs the control cycle, then forwards
to the platforms: the whole-home climate entity, the tuning number/switch/
select entities, and the diagnostic sensors.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.helpers import entity_registry as er

from .const import (
    CONF_ACS,
    CONF_TRVS,
    CONFIG_ENTRY_VERSION,
    DEFAULT_PRESETS,
    PLATFORMS,
    PRESET_BOOST,
)
from .coordinator import SmartClimateConfigEntry, SmartClimateCoordinator
from .persistence import async_remove_stores
from .settings import enabled_presets, preset_number_key

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

# unique_id suffixes of entities retired by later versions; their registry
# entries are pruned at setup so upgrades don't leave orphans behind.
# - _mpc_heating_gain/_mpc_heat_loss/_mpc_model_error: folded into the
#   per-TRV MPC learning-status sensor's attributes.
_RETIRED_UNIQUE_ID_SUFFIXES = (
    "_mpc_heating_gain",
    "_mpc_heat_loss",
    "_mpc_model_error",
)

# Suffixes of the per-managed-device diagnostic entities (unique_id is
# ``{entry_id}_{device_entity_id}_{suffix}``). Used to drop the orphans left
# behind when a device is removed from the selection — see sensor.py.
_PER_DEVICE_SUFFIXES = (
    "device_action",
    "device_runtime",
    "device_cycles_per_hour",
    "valve_position",
    "mpc_learning_status",
)


def _async_remove_retired_entities(
    hass: HomeAssistant, entry: SmartClimateConfigEntry
) -> None:
    """Drop registry entries for entities this configuration no longer creates.

    Covers entities retired by upgrades (fixed suffixes above), the setpoint
    numbers of presets deselected in the options flow, and the per-device
    diagnostic sensors of devices removed from the selection — without this,
    all three linger in the registry as permanently-unavailable orphans.
    """
    config = {**entry.data, **entry.options}
    selected = set(enabled_presets(config))
    deselected_ids = {
        f"{entry.entry_id}_{preset_number_key(preset, edge)}"
        for preset in DEFAULT_PRESETS
        if preset not in selected
        for edge in ("heat", "cool")
    }
    if PRESET_BOOST not in selected:
        deselected_ids.update(
            (f"{entry.entry_id}_boost_offset", f"{entry.entry_id}_boost_duration")
        )
    # Per-device diagnostic entities the *current* device selection should have.
    managed = [*config.get(CONF_TRVS, []), *config.get(CONF_ACS, [])]
    expected_device_ids = {
        f"{entry.entry_id}_{device}_{suffix}"
        for device in managed
        for suffix in _PER_DEVICE_SUFFIXES
    }
    prefix = f"{entry.entry_id}_"
    registry = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        uid = entity.unique_id
        # A per-device-shaped unique_id whose device is no longer managed.
        orphan_device = (
            uid.startswith(prefix)
            and any(uid.endswith(f"_{suffix}") for suffix in _PER_DEVICE_SUFFIXES)
            and uid not in expected_device_ids
        )
        if (
            uid.endswith(_RETIRED_UNIQUE_ID_SUFFIXES)
            or uid in deselected_ids
            or orphan_device
        ):
            registry.async_remove(entity.entity_id)


async def async_remove_entry(
    hass: HomeAssistant, entry: SmartClimateConfigEntry
) -> None:
    """Clean up the entry's persisted learned state (.storage files)."""
    await async_remove_stores(hass, entry.entry_id)


async def async_migrate_entry(
    _hass: HomeAssistant, entry: SmartClimateConfigEntry
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
    _async_remove_retired_entities(hass, entry)
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
