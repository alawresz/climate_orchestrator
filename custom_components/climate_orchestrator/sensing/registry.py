"""Resolve area-configured sensors and compute home-wide aggregates.

Each managed climate device is matched to the temperature/humidity sensor
*configured on its Home Assistant area* (Settings -> Areas -> Related sensors),
not by scanning entities. The home-wide average is taken over the available
area sensors only; offline sensors and devices are handled gracefully
(DESIGN.md §4 and §6.4).
"""

from __future__ import annotations

from datetime import datetime

from homeassistant.const import STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import (
    area_registry as ar,
)
from homeassistant.helpers import (
    device_registry as dr,
)
from homeassistant.helpers import (
    entity_registry as er,
)
from homeassistant.util import dt as dt_util

from ..models import DeviceReading, SmartClimateData, Status
from .aggregate import mean_or_none

# binary_sensor device classes that count as a window/door being open.
_WINDOW_CLASSES = frozenset({"window", "door", "opening", "garage_door"})


@callback
def resolve_area_id(hass: HomeAssistant, entity_id: str) -> str | None:
    """Resolve the area for an entity: its own area, else its device's area."""
    entity_reg = er.async_get(hass)
    entry = entity_reg.async_get(entity_id)
    if entry is None:
        return None
    if entry.area_id is not None:
        return entry.area_id
    if entry.device_id is not None:
        device = dr.async_get(hass).async_get(entry.device_id)
        if device is not None:
            return device.area_id
    return None


@callback
def _read_sensor(
    hass: HomeAssistant,
    entity_id: str | None,
    now: datetime,
    max_age_seconds: float,
) -> tuple[float | None, bool]:
    """Return ``(value, is_stale)`` for a numeric sensor.

    A reading older than ``max_age_seconds`` (when > 0) is reported as missing
    and flagged stale, so a frozen-but-"available" sensor can't drive control.
    Staleness is measured from ``last_reported`` (the last time the sensor sent
    anything), falling back to ``last_updated``.
    """
    if entity_id is None:
        return None, False
    state = hass.states.get(entity_id)
    if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
        return None, False
    try:
        value = float(state.state)
    except (TypeError, ValueError):
        return None, False
    if max_age_seconds > 0.0:
        last = state.last_reported or state.last_updated
        if last is not None and (now - last).total_seconds() > max_age_seconds:
            return None, True
    return value, False


@callback
def _is_available(hass: HomeAssistant, entity_id: str) -> bool:
    """Whether a managed device entity is currently usable."""
    state = hass.states.get(entity_id)
    return state is not None and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN)


@callback
def window_sensors_in_area(hass: HomeAssistant, area_id: str) -> list[str]:
    """Window/door binary sensors belonging to an area (entity or device level)."""
    entity_reg = er.async_get(hass)
    device_reg = dr.async_get(hass)
    entries = {
        entry.entity_id: entry
        for entry in er.async_entries_for_area(entity_reg, area_id)
    }
    for device in dr.async_entries_for_area(device_reg, area_id):
        for entry in er.async_entries_for_device(entity_reg, device.id):
            if (entry.area_id or device.area_id) == area_id:
                entries[entry.entity_id] = entry

    return [
        entity_id
        for entity_id, entry in entries.items()
        if entry.domain == "binary_sensor"
        and (entry.device_class or entry.original_device_class) in _WINDOW_CLASSES
    ]


@callback
def _any_on(hass: HomeAssistant, entity_ids: list[str]) -> bool:
    """Whether any of the given binary sensors is currently on."""
    return any(
        (state := hass.states.get(entity_id)) is not None and state.state == STATE_ON
        for entity_id in entity_ids
    )


@callback
def build_snapshot(
    hass: HomeAssistant,
    device_ids: list[str],
    *,
    outdoor_sensor: str | None = None,
    max_age_seconds: float = 0.0,
    now: datetime | None = None,
) -> SmartClimateData:
    """Build the per-cycle snapshot from the current HA state.

    Area sensors older than ``max_age_seconds`` are treated as missing and
    collected into ``stale_sensors`` (so a frozen sensor doesn't drive control).
    """
    area_reg = ar.async_get(hass)
    when = now if now is not None else dt_util.utcnow()
    value_cache: dict[str, float | None] = {}
    stale: set[str] = set()

    def resolve(entity_id: str | None) -> float | None:
        if entity_id is None:
            return None
        if entity_id not in value_cache:
            val, is_stale = _read_sensor(hass, entity_id, when, max_age_seconds)
            value_cache[entity_id] = val
            if is_stale:
                stale.add(entity_id)
        return value_cache[entity_id]

    readings: dict[str, DeviceReading] = {}
    temp_sensors: set[str] = set()
    humidity_sensors: set[str] = set()
    window_sensors: set[str] = set()
    window_open_by_area: dict[str, bool] = {}

    for entity_id in device_ids:
        area_id = resolve_area_id(hass, entity_id)
        temp_sensor: str | None = None
        humidity_sensor: str | None = None
        window_open = False
        if area_id is not None:
            area = area_reg.async_get_area(area_id)
            if area is not None:
                temp_sensor = area.temperature_entity_id
                humidity_sensor = area.humidity_entity_id
            if area_id not in window_open_by_area:
                area_windows = window_sensors_in_area(hass, area_id)
                window_sensors.update(area_windows)
                window_open_by_area[area_id] = _any_on(hass, area_windows)
            window_open = window_open_by_area[area_id]

        if temp_sensor is not None:
            temp_sensors.add(temp_sensor)
        if humidity_sensor is not None:
            humidity_sensors.add(humidity_sensor)

        readings[entity_id] = DeviceReading(
            entity_id=entity_id,
            available=_is_available(hass, entity_id),
            area_id=area_id,
            area_temperature_sensor=temp_sensor,
            area_humidity_sensor=humidity_sensor,
            area_temperature=resolve(temp_sensor),
            area_humidity=resolve(humidity_sensor),
            window_open=window_open,
        )

    home_avg_temperature = mean_or_none(resolve(s) for s in temp_sensors)
    home_avg_humidity = mean_or_none(resolve(s) for s in humidity_sensors)

    available = frozenset(eid for eid, r in readings.items() if r.available)
    unavailable = frozenset(eid for eid, r in readings.items() if not r.available)

    tracked: set[str] = (
        set(device_ids) | temp_sensors | humidity_sensors | window_sensors
    )
    if outdoor_sensor is not None:
        tracked.add(outdoor_sensor)

    return SmartClimateData(
        home_avg_temperature=home_avg_temperature,
        home_avg_humidity=home_avg_humidity,
        available_devices=available,
        unavailable_devices=unavailable,
        readings=readings,
        tracked_entities=frozenset(tracked),
        stale_sensors=frozenset(stale),
        # A warm-up-unaware best effort; the coordinator refines this to
        # ``INITIALIZING`` during the post-restart grace window.
        status=Status.DEGRADED if unavailable else Status.OK,
    )
