"""Tests for area-sensor resolution and home-wide aggregation."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta

from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from custom_components.climate_orchestrator.models import HomeAvgSource
from custom_components.climate_orchestrator.sensing.registry import build_snapshot
from tests.conftest import (
    AC_ENTITY,
    AREA_HUMIDITY_SENSOR,
    AREA_TEMP_SENSOR,
    TRV_ENTITY,
)


async def test_resolves_area_sensors_and_home_average(
    hass: HomeAssistant,
    living_area: str,
    register_entity_in_area: Callable[[str, str | None], str],
) -> None:
    """A device resolves to its area sensors and feeds the home average."""
    register_entity_in_area(TRV_ENTITY, living_area)
    hass.states.async_set(TRV_ENTITY, "heat")
    hass.states.async_set(AREA_TEMP_SENSOR, "20.0")
    hass.states.async_set(AREA_HUMIDITY_SENSOR, "50")

    data = build_snapshot(hass, [TRV_ENTITY])

    assert data.home_avg_temperature == 20.0
    assert data.home_avg_humidity == 50.0
    reading = data.readings[TRV_ENTITY]
    assert reading.area_temperature_sensor == AREA_TEMP_SENSOR
    assert reading.area_temperature == 20.0
    assert data.available_devices == frozenset({TRV_ENTITY})
    assert not data.degraded


async def test_offline_sensor_dropped_from_average(
    hass: HomeAssistant,
    living_area: str,
    register_entity_in_area: Callable[[str, str | None], str],
) -> None:
    """An unavailable area sensor drops out instead of poisoning the mean."""
    register_entity_in_area(TRV_ENTITY, living_area)
    hass.states.async_set(TRV_ENTITY, "heat")
    hass.states.async_set(AREA_TEMP_SENSOR, STATE_UNAVAILABLE)

    data = build_snapshot(hass, [TRV_ENTITY])

    assert data.home_avg_temperature is None
    assert data.readings[TRV_ENTITY].area_temperature is None


async def test_unavailable_device_is_degraded_but_average_survives(
    hass: HomeAssistant,
    living_area: str,
    register_entity_in_area: Callable[[str, str | None], str],
) -> None:
    """An offline device is flagged degraded; the area average still computes."""
    register_entity_in_area(TRV_ENTITY, living_area)
    hass.states.async_set(TRV_ENTITY, STATE_UNAVAILABLE)
    hass.states.async_set(AREA_TEMP_SENSOR, "19.0")

    data = build_snapshot(hass, [TRV_ENTITY])

    assert data.unavailable_devices == frozenset({TRV_ENTITY})
    assert data.degraded
    assert data.home_avg_temperature == 19.0


async def test_device_without_area_has_no_sensors(hass: HomeAssistant) -> None:
    """A device with no area resolves to no sensors and no aggregate."""
    hass.states.async_set(TRV_ENTITY, "heat")

    data = build_snapshot(hass, [TRV_ENTITY])

    reading = data.readings[TRV_ENTITY]
    assert reading.area_id is None
    assert reading.area_temperature_sensor is None
    assert data.home_avg_temperature is None


async def test_two_areas_average_together(
    hass: HomeAssistant,
    living_area: str,
    register_entity_in_area: Callable[[str, str | None], str],
) -> None:
    """The home average spans every distinct area sensor in use."""
    bedroom_temp = "sensor.bedroom_temperature"
    hass.states.async_set(bedroom_temp, "23.0", {"device_class": "temperature"})
    area_reg = ar.async_get(hass)
    bedroom = area_reg.async_get_or_create("Bedroom")
    area_reg.async_update(bedroom.id, temperature_entity_id=bedroom_temp)

    register_entity_in_area(TRV_ENTITY, living_area)
    register_entity_in_area(AC_ENTITY, bedroom.id)
    hass.states.async_set(TRV_ENTITY, "heat")
    hass.states.async_set(AC_ENTITY, "cool")
    hass.states.async_set(AREA_TEMP_SENSOR, "21.0")

    data = build_snapshot(hass, [TRV_ENTITY, AC_ENTITY])

    # Living 21.0 + Bedroom 23.0 -> 22.0
    assert data.home_avg_temperature == 22.0


async def test_window_open_detected_from_area_binary_sensor(
    hass: HomeAssistant,
    living_area: str,
    register_entity_in_area: Callable[[str, str | None], str],
) -> None:
    """An open window/door binary sensor in the area flags the device."""
    register_entity_in_area(TRV_ENTITY, living_area)
    hass.states.async_set(TRV_ENTITY, "heat")
    hass.states.async_set(AREA_TEMP_SENSOR, "21.0")

    registry = er.async_get(hass)
    window = registry.async_get_or_create(
        "binary_sensor",
        "test",
        "u_window",
        suggested_object_id="living_window",
        original_device_class="window",
    )
    registry.async_update_entity(window.entity_id, area_id=living_area)

    hass.states.async_set(window.entity_id, "on")
    assert build_snapshot(hass, [TRV_ENTITY]).readings[TRV_ENTITY].window_open is True

    hass.states.async_set(window.entity_id, "off")
    assert build_snapshot(hass, [TRV_ENTITY]).readings[TRV_ENTITY].window_open is False


async def test_home_override_sensor_replaces_computed_average(
    hass: HomeAssistant,
    living_area: str,
    register_entity_in_area: Callable[[str, str | None], str],
) -> None:
    """User-provided home sensors override the computed mean and are tracked."""
    register_entity_in_area(TRV_ENTITY, living_area)
    hass.states.async_set(TRV_ENTITY, "heat")
    hass.states.async_set(AREA_TEMP_SENSOR, "20.0")
    hass.states.async_set(AREA_HUMIDITY_SENSOR, "50")
    hass.states.async_set("sensor.whole_home_temp", "23.5")

    data = build_snapshot(hass, [TRV_ENTITY], home_temp_sensor="sensor.whole_home_temp")

    assert data.home_avg_temperature == 23.5
    assert data.home_temp_source is HomeAvgSource.EXTERNAL
    # Humidity has no override: computed, from the area sensor.
    assert data.home_avg_humidity == 50.0
    assert data.home_humidity_source is HomeAvgSource.COMPUTED
    # The override is tracked so its state changes re-trigger the update.
    assert "sensor.whole_home_temp" in data.tracked_entities
    # Per-device readings still come from the *area* sensor, not the override.
    assert data.readings[TRV_ENTITY].area_temperature == 20.0


async def test_unusable_home_override_falls_back_to_computed(
    hass: HomeAssistant,
    living_area: str,
    register_entity_in_area: Callable[[str, str | None], str],
) -> None:
    """An unavailable/stale override falls back to the computed mean."""
    register_entity_in_area(TRV_ENTITY, living_area)
    hass.states.async_set(TRV_ENTITY, "heat")
    hass.states.async_set(AREA_TEMP_SENSOR, "20.0")
    hass.states.async_set("sensor.whole_home_temp", STATE_UNAVAILABLE)

    data = build_snapshot(hass, [TRV_ENTITY], home_temp_sensor="sensor.whole_home_temp")

    assert data.home_avg_temperature == 20.0
    assert data.home_temp_source is HomeAvgSource.FALLBACK


async def test_stale_home_override_falls_back_to_computed(
    hass: HomeAssistant,
    living_area: str,
    register_entity_in_area: Callable[[str, str | None], str],
) -> None:
    """The staleness guard applies to the override like any other sensor."""
    register_entity_in_area(TRV_ENTITY, living_area)
    hass.states.async_set(TRV_ENTITY, "heat")
    hass.states.async_set(AREA_TEMP_SENSOR, "20.0")
    hass.states.async_set("sensor.whole_home_temp", "30.0")

    later = dt_util.utcnow() + timedelta(hours=2)
    data = build_snapshot(
        hass,
        [TRV_ENTITY],
        home_temp_sensor="sensor.whole_home_temp",
        max_age_seconds=3600.0,
        now=later,
    )

    # Both the area sensor and the override are older than the cutoff: the
    # override is flagged stale and the computed mean is empty too.
    assert data.home_avg_temperature is None
    assert data.home_temp_source is HomeAvgSource.FALLBACK
    assert "sensor.whole_home_temp" in data.stale_sensors


async def test_non_finite_sensor_reading_is_dropped(
    hass: HomeAssistant,
    living_area: str,
    register_entity_in_area: Callable[[str, str | None], str],
) -> None:
    """A sensor reporting 'nan' is treated as missing, not averaged.

    float("nan") parses without raising, so without the finiteness guard a
    single such reading would silently poison the home average (NaN compares
    False against everything, freezing control).
    """
    register_entity_in_area(TRV_ENTITY, living_area)
    hass.states.async_set(TRV_ENTITY, "heat")
    hass.states.async_set(AREA_TEMP_SENSOR, "nan")

    data = build_snapshot(hass, [TRV_ENTITY])
    assert data.readings[TRV_ENTITY].area_temperature is None
    assert data.home_avg_temperature is None
