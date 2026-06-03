"""User-adjustable numeric tuning parameters (persisted)."""

from __future__ import annotations

from homeassistant.components.number import NumberMode, RestoreNumber
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import SmartClimateConfigEntry, SmartClimateCoordinator
from .entity import hub_device_info
from .settings import NUMBER_SETTINGS, PRESET_NUMBER_SETTINGS, NumberSetting


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SmartClimateConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the tuning and per-preset number entities."""
    coordinator = entry.runtime_data
    async_add_entities(
        SmartClimateNumber(coordinator, setting)
        for setting in (*NUMBER_SETTINGS, *PRESET_NUMBER_SETTINGS)
    )


class SmartClimateNumber(RestoreNumber):
    """A persisted, runtime-adjustable control parameter (unit per setting)."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX

    def __init__(
        self, coordinator: SmartClimateCoordinator, setting: NumberSetting
    ) -> None:
        """Initialise from a setting description."""
        self._coordinator = coordinator
        self._setting = setting
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{setting.key}"
        self._attr_translation_key = setting.key
        self._attr_native_unit_of_measurement = setting.unit
        self._attr_native_min_value = setting.min_value
        self._attr_native_max_value = setting.max_value
        self._attr_native_step = setting.step
        self._attr_native_value = setting.default
        self._attr_device_info = hub_device_info(coordinator.entry.entry_id)

    async def async_added_to_hass(self) -> None:
        """Restore the last set value across restarts."""
        await super().async_added_to_hass()
        last = await self.async_get_last_number_data()
        if last is not None and last.native_value is not None:
            self._attr_native_value = last.native_value

    async def async_set_native_value(self, value: float) -> None:
        """Persist a new value and re-run control."""
        self._attr_native_value = value
        self.async_write_ha_state()
        await self._coordinator.async_refresh()
