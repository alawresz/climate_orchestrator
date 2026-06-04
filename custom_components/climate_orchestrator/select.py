"""Calibration-mode select: how TRVs are driven."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.select import SelectEntity
from homeassistant.helpers.restore_state import RestoreEntity

from .const import CALIBRATION_MODES, DEFAULT_CALIBRATION_MODE
from .entity import hub_device_info

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from .coordinator import SmartClimateConfigEntry, SmartClimateCoordinator

# Writes are funneled through the coordinator; entity updates are pushed
# snapshots, so platform-level update serialization is unnecessary.
PARALLEL_UPDATES = 0

CALIBRATION_MODE_KEY = "calibration_mode"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SmartClimateConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the calibration-mode select."""
    async_add_entities([SmartClimateCalibrationSelect(entry.runtime_data)])


class SmartClimateCalibrationSelect(SelectEntity, RestoreEntity):
    """Chooses how TRVs are driven: target setpoint, MPC, or offset."""

    # No entity_category: this is an operational control, so it shows in the
    # device's "Controls" section rather than "Configuration".
    _attr_has_entity_name = True
    _attr_translation_key = CALIBRATION_MODE_KEY
    _attr_options = CALIBRATION_MODES

    def __init__(self, coordinator: SmartClimateCoordinator) -> None:
        """Initialise the select bound to the hub device."""
        self._coordinator = coordinator
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{CALIBRATION_MODE_KEY}"
        self._attr_current_option = DEFAULT_CALIBRATION_MODE
        self._attr_device_info = hub_device_info(coordinator.entry.entry_id)

    async def async_added_to_hass(self) -> None:
        """Restore the last selected mode across restarts."""
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state in CALIBRATION_MODES:
            self._attr_current_option = last.state

    async def async_select_option(self, option: str) -> None:
        """Persist the chosen mode and re-run control."""
        self._attr_current_option = option
        self.async_write_ha_state()
        await self._coordinator.async_refresh()
