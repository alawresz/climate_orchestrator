"""Tests for the Repairs (issue registry) integration."""

from __future__ import annotations

from collections.abc import Callable
import time

from homeassistant.const import ATTR_ENTITY_ID, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import issue_registry as ir
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.climate_orchestrator.const import (
    CONTROL_FAILURE_ISSUE_THRESHOLD,
    DOMAIN,
)
from custom_components.climate_orchestrator.coordinator import SmartClimateCoordinator
from tests.conftest import AC_ENTITY, AREA_HUMIDITY_SENSOR, AREA_TEMP_SENSOR, TRV_ENTITY


async def _refresh(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    coordinator: SmartClimateCoordinator = entry.runtime_data
    await coordinator.async_refresh()
    await hass.async_block_till_done()


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
    await _refresh(hass, init_integration)
    assert registry.async_get_issue(DOMAIN, "outdoor_sensor_missing") is not None

    await hass.services.async_call(
        "switch", "turn_off", {ATTR_ENTITY_ID: switch}, blocking=True
    )
    await _refresh(hass, init_integration)
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
    await _refresh(hass, init_integration)
    assert registry.async_get_issue(DOMAIN, "inverted_band") is not None

    # Restore a sane band -> the issue clears.
    await _set(heat_num, 20.5)
    await _set(cool_num, 24.5)
    await _refresh(hass, init_integration)
    assert registry.async_get_issue(DOMAIN, "inverted_band") is None


async def test_no_temperature_source_raises_issue(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Losing every temperature source raises the no-source repair issue."""
    registry = ir.async_get(hass)
    assert registry.async_get_issue(DOMAIN, "no_temperature_source") is None

    for entity in (TRV_ENTITY, AC_ENTITY, AREA_TEMP_SENSOR, AREA_HUMIDITY_SENSOR):
        hass.states.async_set(entity, STATE_UNAVAILABLE)
    await _refresh(hass, init_integration)

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
        await _refresh(hass, init_integration)
    assert registry.async_get_issue(DOMAIN, "control_loop_failing") is None

    # The threshold-th consecutive failure surfaces the repair.
    await _refresh(hass, init_integration)
    assert registry.async_get_issue(DOMAIN, "control_loop_failing") is not None

    # The next clean cycle clears it (and resets the counter).
    monkeypatch.undo()
    await _refresh(hass, init_integration)
    assert registry.async_get_issue(DOMAIN, "control_loop_failing") is None


_IGNORED_ISSUE = f"device_ignoring_commands_{TRV_ENTITY}"


async def _start_ignored_streak(
    hass: HomeAssistant, entry: MockConfigEntry
) -> SmartClimateCoordinator:
    """Mock succeeding climate services and run until the watchdog is armed.

    The fixture TRV reports ``heat`` while a 21 °C room (inside the band)
    commands ``off`` — with the service calls now *succeeding*, that's a
    silently non-compliant device. Two cycles: the first still sees the
    setup-phase command_failing latch (the fixture had no climate services),
    the second starts the streak.
    """
    async_mock_service(hass, "climate", "set_hvac_mode")
    async_mock_service(hass, "climate", "set_temperature")
    await _refresh(hass, entry)
    await _refresh(hass, entry)
    coordinator: SmartClimateCoordinator = entry.runtime_data
    assert coordinator._runtime(TRV_ENTITY).ignored_since is not None
    return coordinator


async def test_command_ignored_watchdog_raises_and_clears(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """A device that takes commands but never applies them raises a repair."""
    registry = ir.async_get(hass)
    coordinator = await _start_ignored_streak(hass, init_integration)
    # Streak running but young: no issue yet.
    assert registry.async_get_issue(DOMAIN, _IGNORED_ISSUE) is None

    # Pretend the divergence has persisted past the watchdog threshold.
    coordinator._runtime(TRV_ENTITY).ignored_since = time.monotonic() - 999.0
    await _refresh(hass, init_integration)
    assert registry.async_get_issue(DOMAIN, _IGNORED_ISSUE) is not None

    # The device finally applies the commanded mode -> issue clears.
    hass.states.async_set(TRV_ENTITY, "off")
    await _refresh(hass, init_integration)
    assert registry.async_get_issue(DOMAIN, _IGNORED_ISSUE) is None
    assert coordinator._runtime(TRV_ENTITY).ignored_since is None


async def test_loud_command_failures_do_not_raise_ignored_issue(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Failing service calls are the log-once latch's job, not the watchdog's."""
    registry = ir.async_get(hass)
    coordinator: SmartClimateCoordinator = init_integration.runtime_data

    # Deterministic outage: the climate services exist but reject every command
    # (a missing entity alone only warns — the call itself would succeed).
    async def _device_rejects(call: ServiceCall) -> None:
        raise HomeAssistantError

    hass.services.async_register("climate", "set_hvac_mode", _device_rejects)
    hass.services.async_register("climate", "set_temperature", _device_rejects)
    await _refresh(hass, init_integration)
    await _refresh(hass, init_integration)

    assert coordinator._runtime(TRV_ENTITY).command_failing
    assert coordinator._runtime(TRV_ENTITY).ignored_since is None
    assert registry.async_get_issue(DOMAIN, _IGNORED_ISSUE) is None


async def test_unavailable_device_clears_ignored_issue(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """A device dropping offline is 'unavailable', not 'ignoring commands'."""
    registry = ir.async_get(hass)
    coordinator = await _start_ignored_streak(hass, init_integration)
    coordinator._runtime(TRV_ENTITY).ignored_since = time.monotonic() - 999.0
    await _refresh(hass, init_integration)
    assert registry.async_get_issue(DOMAIN, _IGNORED_ISSUE) is not None

    hass.states.async_set(TRV_ENTITY, STATE_UNAVAILABLE)
    await _refresh(hass, init_integration)
    assert registry.async_get_issue(DOMAIN, _IGNORED_ISSUE) is None
    assert coordinator._runtime(TRV_ENTITY).ignored_since is None
