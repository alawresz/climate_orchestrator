"""User-toggleable feature flags (persisted)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .coordinator import SmartClimateConfigEntry, SmartClimateCoordinator
from .entity import hub_device_info
from .settings import SWITCH_SETTINGS, SwitchSetting


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SmartClimateConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the feature-flag switches."""
    coordinator = entry.runtime_data
    async_add_entities(
        SmartClimateSwitch(coordinator, setting) for setting in SWITCH_SETTINGS
    )


class SmartClimateSwitch(SwitchEntity, RestoreEntity):
    """A persisted feature toggle that re-runs control when changed."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self, coordinator: SmartClimateCoordinator, setting: SwitchSetting
    ) -> None:
        """Initialise from a setting description."""
        self._coordinator = coordinator
        self._setting = setting
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{setting.key}"
        self._attr_translation_key = setting.key
        self._attr_is_on = setting.default
        self._attr_device_info = hub_device_info(coordinator.entry.entry_id)

    async def async_added_to_hass(self) -> None:
        """Restore the last on/off state across restarts."""
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None:
            self._attr_is_on = last.state == "on"

    async def _set(self, is_on: bool) -> None:
        self._attr_is_on = is_on
        self.async_write_ha_state()
        await self._coordinator.async_refresh()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable the feature."""
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable the feature."""
        await self._set(False)
