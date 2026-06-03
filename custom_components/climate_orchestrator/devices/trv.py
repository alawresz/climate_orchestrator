"""TRV-specific helpers: locate calibration entities and compute the offset.

SONOFF TRVZB (and similar Zigbee2MQTT valves) expose a ``valve_opening_degree``
and a ``local_temperature_calibration`` number on the same device as the climate
entity. We discover those by inspecting the device's entities so we don't hard
code entity IDs, and fall back gracefully when they're absent.
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er

VALVE_OPENING_HINTS = ("valve_opening_degree", "valve_opening", "valve_position")
LOCAL_CALIBRATION_HINTS = (
    "local_temperature_calibration",
    "temperature_calibration",
    "temperature_offset",
)
_MAX_OFFSET = 10.0


@callback
def find_related_number(
    hass: HomeAssistant, climate_entity_id: str, hints: tuple[str, ...]
) -> str | None:
    """Find a ``number`` entity on the climate's device matching a hint."""
    registry = er.async_get(hass)
    entry = registry.async_get(climate_entity_id)
    if entry is None or entry.device_id is None:
        return None
    for candidate in er.async_entries_for_device(
        registry, entry.device_id, include_disabled_entities=False
    ):
        if candidate.domain != "number":
            continue
        haystack = f"{candidate.unique_id} {candidate.entity_id}".lower()
        if any(hint in haystack for hint in hints):
            return candidate.entity_id
    return None


def local_offset(
    area_temp: float | None, trv_internal_temp: float | None
) -> float | None:
    """Offset that makes the TRV behave as if it read the area temperature.

    ``effective = trv_internal + offset``, so ``offset = area - trv_internal``,
    clamped to a sane range.
    """
    if area_temp is None or trv_internal_temp is None:
        return None
    offset = area_temp - trv_internal_temp
    return round(max(-_MAX_OFFSET, min(_MAX_OFFSET, offset)), 1)
