"""Tests for the area-sensor staleness guard in the snapshot builder."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.climate_orchestrator.sensing.registry import build_snapshot
from tests.conftest import AC_ENTITY, AREA_TEMP_SENSOR, TRV_ENTITY


async def test_fresh_sensor_is_used(
    hass: HomeAssistant,
    living_area: str,
    register_entity_in_area: Callable[[str, str | None], str],
) -> None:
    """A recently-reported sensor is read normally and not flagged stale."""
    register_entity_in_area(TRV_ENTITY, living_area)
    register_entity_in_area(AC_ENTITY, living_area)
    hass.states.async_set(TRV_ENTITY, "heat")
    hass.states.async_set(AC_ENTITY, "off")

    data = build_snapshot(hass, [TRV_ENTITY, AC_ENTITY], max_age_seconds=600.0)

    assert not data.stale_sensors
    assert data.readings[TRV_ENTITY].area_temperature == 21.0
    assert data.home_avg_temperature == 21.0


async def test_stale_sensor_is_dropped_and_flagged(
    hass: HomeAssistant,
    living_area: str,
    register_entity_in_area: Callable[[str, str | None], str],
) -> None:
    """A reading older than the max age is treated as missing and flagged."""
    register_entity_in_area(TRV_ENTITY, living_area)
    register_entity_in_area(AC_ENTITY, living_area)
    hass.states.async_set(TRV_ENTITY, "heat")
    hass.states.async_set(AC_ENTITY, "off")

    # Evaluate as if an hour has passed with no new reports.
    later = dt_util.utcnow() + timedelta(hours=1)
    data = build_snapshot(
        hass, [TRV_ENTITY, AC_ENTITY], max_age_seconds=600.0, now=later
    )

    assert AREA_TEMP_SENSOR in data.stale_sensors
    assert data.readings[TRV_ENTITY].area_temperature is None
    # The only temperature source was stale, so the home average is unknown too.
    assert data.home_avg_temperature is None


async def test_disabled_when_max_age_zero(
    hass: HomeAssistant,
    living_area: str,
    register_entity_in_area: Callable[[str, str | None], str],
) -> None:
    """A max age of 0 disables the guard entirely (back-compatible)."""
    register_entity_in_area(TRV_ENTITY, living_area)
    hass.states.async_set(TRV_ENTITY, "heat")

    later = dt_util.utcnow() + timedelta(days=7)
    data = build_snapshot(hass, [TRV_ENTITY], max_age_seconds=0.0, now=later)

    assert not data.stale_sensors
    assert data.readings[TRV_ENTITY].area_temperature == 21.0
