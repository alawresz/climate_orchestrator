"""Tests for the Repairs (issue registry) integration."""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.const import ATTR_ENTITY_ID, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
)

from custom_components.climate_orchestrator.const import (
    CONTROL_FAILURE_ISSUE_THRESHOLD,
    DOMAIN,
)
from custom_components.climate_orchestrator.coordinator import SmartClimateCoordinator
from tests.conftest import AC_ENTITY, AREA_HUMIDITY_SENSOR, AREA_TEMP_SENSOR, TRV_ENTITY
from tests.ha.helpers import refresh


async def test_adaptive_comfort_without_outdoor_sensor_raises_and_clears(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """Enabling adaptive comfort with no outdoor sensor raises a repair issue."""
    registry = ir.async_get(hass)
    cid = init_integration.entry_id
    # No outdoor sensor configured, adaptive comfort off by default -> no issue.
    assert registry.async_get_issue(DOMAIN, "outdoor_sensor_missing") is None

    switch = entity_id_for("switch", f"{cid}_adaptive_cooling_comfort")
    await hass.services.async_call(
        "switch", "turn_on", {ATTR_ENTITY_ID: switch}, blocking=True
    )
    await refresh(hass, init_integration)
    assert registry.async_get_issue(DOMAIN, "outdoor_sensor_missing") is not None

    await hass.services.async_call(
        "switch", "turn_off", {ATTR_ENTITY_ID: switch}, blocking=True
    )
    await refresh(hass, init_integration)
    assert registry.async_get_issue(DOMAIN, "outdoor_sensor_missing") is None


async def test_inverted_band_raises_and_clears(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """Inverting a preset's edges (via the number entities) raises the issue.

    The climate ``set_temperature`` service rejects low > high, so the real way
    a user can invert a band is by editing the independent per-preset heat/cool
    number entities.
    """
    registry = ir.async_get(hass)
    assert registry.async_get_issue(DOMAIN, "inverted_band") is None
    cid = init_integration.entry_id
    heat_num = entity_id_for("number", f"{cid}_preset_home_heat")
    cool_num = entity_id_for("number", f"{cid}_preset_home_cool")

    async def _set(entity: str, value: float) -> None:
        await hass.services.async_call(
            "number",
            "set_value",
            {ATTR_ENTITY_ID: entity, "value": value},
            blocking=True,
        )

    # Push the cool edge below the heat edge -> inverted (no neutral zone).
    await _set(cool_num, 22.0)
    await _set(heat_num, 24.0)
    await refresh(hass, init_integration)
    assert registry.async_get_issue(DOMAIN, "inverted_band") is not None

    # Restore a sane band -> the issue clears.
    await _set(heat_num, 20.5)
    await _set(cool_num, 24.5)
    await refresh(hass, init_integration)
    assert registry.async_get_issue(DOMAIN, "inverted_band") is None


async def test_no_temperature_source_raises_issue(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Losing every temperature source raises the no-source repair issue."""
    registry = ir.async_get(hass)
    assert registry.async_get_issue(DOMAIN, "no_temperature_source") is None

    for entity in (TRV_ENTITY, AC_ENTITY, AREA_TEMP_SENSOR, AREA_HUMIDITY_SENSOR):
        hass.states.async_set(entity, STATE_UNAVAILABLE)
    await refresh(hass, init_integration)

    assert registry.async_get_issue(DOMAIN, "no_temperature_source") is not None


async def test_repeated_control_failures_raise_and_clear(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A repeatedly failing control cycle raises a repair; success clears it."""
    registry = ir.async_get(hass)
    coordinator: SmartClimateCoordinator = init_integration.runtime_data

    async def _boom(data: object) -> None:
        raise RuntimeError

    monkeypatch.setattr(coordinator, "_async_control", _boom)
    # One failure short of the threshold: contained, no repair yet.
    for _ in range(CONTROL_FAILURE_ISSUE_THRESHOLD - 1):
        await refresh(hass, init_integration)
    assert registry.async_get_issue(DOMAIN, "control_loop_failing") is None

    # The threshold-th consecutive failure surfaces the repair.
    await refresh(hass, init_integration)
    assert registry.async_get_issue(DOMAIN, "control_loop_failing") is not None

    # The next clean cycle clears it (and resets the counter).
    monkeypatch.undo()
    await refresh(hass, init_integration)
    assert registry.async_get_issue(DOMAIN, "control_loop_failing") is None
