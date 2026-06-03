"""Shared base entity for Climate Orchestrator."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEFAULT_TITLE, DOMAIN, MANUFACTURER, MODEL
from .coordinator import SmartClimateCoordinator


def hub_device_info(entry_id: str) -> DeviceInfo:
    """The single whole-home hub device all entities belong to."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry_id)},
        name=DEFAULT_TITLE,
        manufacturer=MANUFACTURER,
        model=MODEL,
    )


class SmartClimateBaseEntity(CoordinatorEntity[SmartClimateCoordinator]):
    """Base entity binding all platforms to the single whole-home hub device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: SmartClimateCoordinator) -> None:
        """Initialise the base entity and attach it to the hub device."""
        super().__init__(coordinator)
        self._attr_device_info = hub_device_info(coordinator.entry.entry_id)
