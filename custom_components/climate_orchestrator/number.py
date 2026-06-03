"""User-adjustable numeric tuning parameters (persisted)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.number import NumberMode, RestoreNumber
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.helpers import area_registry as ar

from .const import AREA_BAND_OFFSET_DEFAULT, AREA_BAND_OFFSET_LIMIT, TARGET_TEMP_STEP
from .entity import hub_device_info
from .sensing.registry import resolve_area_id
from .settings import (
    NUMBER_SETTINGS,
    PRESET_NUMBER_SETTINGS,
    NumberSetting,
    area_offset_key,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from .coordinator import SmartClimateConfigEntry, SmartClimateCoordinator


def _managed_area_ids(
    hass: HomeAssistant, coordinator: SmartClimateCoordinator
) -> list[str]:
    """Distinct areas (in device order) that contain a managed device."""
    seen: set[str] = set()
    ordered: list[str] = []
    for entity_id in coordinator.device_ids:
        area_id = resolve_area_id(hass, entity_id)
        if area_id is not None and area_id not in seen:
            seen.add(area_id)
            ordered.append(area_id)
    return ordered


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SmartClimateConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the tuning, per-preset, and per-area number entities."""
    coordinator = entry.runtime_data
    entities: list[RestoreNumber] = [
        SmartClimateNumber(coordinator, setting)
        for setting in (*NUMBER_SETTINGS, *PRESET_NUMBER_SETTINGS)
    ]
    area_reg = ar.async_get(hass)
    for area_id in _managed_area_ids(hass, coordinator):
        area = area_reg.async_get_area(area_id)
        name = area.name if area is not None else area_id
        entities.append(SmartClimateAreaOffsetNumber(coordinator, area_id, name))
    async_add_entities(entities)


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


class SmartClimateAreaOffsetNumber(RestoreNumber):
    """Per-area comfort band offset (°C); positive runs the area warmer."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX
    _attr_translation_key = "area_band_offset"
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_native_min_value = -AREA_BAND_OFFSET_LIMIT
    _attr_native_max_value = AREA_BAND_OFFSET_LIMIT
    _attr_native_step = TARGET_TEMP_STEP

    def __init__(
        self,
        coordinator: SmartClimateCoordinator,
        area_id: str,
        area_name: str,
    ) -> None:
        """Initialise for one area."""
        self._coordinator = coordinator
        key = area_offset_key(area_id)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{key}"
        self._attr_translation_placeholders = {"area": area_name}
        self._attr_native_value = AREA_BAND_OFFSET_DEFAULT
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
