"""Binary sensors for Climate Orchestrator.

* **Operational state** (window open, frost protection active, dehumidifying) —
  handy on dashboards and in automations.

Overall health (initializing / ok / degraded) lives on the `status` *sensor*
instead, which also carries the `unavailable_devices` attribute.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import SmartClimateConfigEntry, SmartClimateCoordinator
from .entity import SmartClimateBaseEntity


@dataclass(frozen=True, kw_only=True)
class SmartClimateBinaryDescription(BinarySensorEntityDescription):
    """Describes a coordinator-backed binary sensor."""

    is_on_fn: Callable[[SmartClimateCoordinator], bool]
    attrs_fn: Callable[[SmartClimateCoordinator], dict[str, Any]] | None = None


def _open_areas(coordinator: SmartClimateCoordinator) -> dict[str, Any]:
    data = coordinator.data
    return {
        "open_areas": sorted(
            {r.area_id for r in data.readings.values() if r.window_open and r.area_id}
        )
    }


BINARY_SENSORS: tuple[SmartClimateBinaryDescription, ...] = (
    SmartClimateBinaryDescription(
        key="window_open",
        translation_key="window_open",
        device_class=BinarySensorDeviceClass.WINDOW,
        is_on_fn=lambda c: c.data.any_window_open,
        attrs_fn=_open_areas,
    ),
    SmartClimateBinaryDescription(
        key="frost_active",
        translation_key="frost_active",
        device_class=BinarySensorDeviceClass.COLD,
        is_on_fn=lambda c: c.frost_active(),
    ),
    SmartClimateBinaryDescription(
        key="dew_point_active",
        translation_key="dew_point_active",
        device_class=BinarySensorDeviceClass.RUNNING,
        is_on_fn=lambda c: c.dew_point_active(),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SmartClimateConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the operational binary sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        SmartClimateBinarySensor(coordinator, description)
        for description in BINARY_SENSORS
    )


class SmartClimateBinarySensor(SmartClimateBaseEntity, BinarySensorEntity):
    """A coordinator-backed binary sensor."""

    entity_description: SmartClimateBinaryDescription

    def __init__(
        self,
        coordinator: SmartClimateCoordinator,
        description: SmartClimateBinaryDescription,
    ) -> None:
        """Initialise the binary sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{description.key}"

    @property
    def is_on(self) -> bool:
        """Whether the sensor's condition currently holds."""
        return self.entity_description.is_on_fn(self.coordinator)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Optional supporting attributes."""
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self.coordinator)
