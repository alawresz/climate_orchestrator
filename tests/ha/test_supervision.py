"""Tests for the device supervision: manual-override takeover + watchdog."""

from __future__ import annotations

from collections.abc import Callable
import time

from homeassistant.const import ATTR_ENTITY_ID, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
    async_mock_service,
)

from custom_components.climate_orchestrator.const import (
    DOMAIN,
    EVENT_CLIMATE_ORCHESTRATOR,
    EVENT_TYPE_IGNORING_ENDED,
    EVENT_TYPE_IGNORING_STARTED,
    EVENT_TYPE_OVERRIDE_ENDED,
    EVENT_TYPE_OVERRIDE_STARTED,
)
from custom_components.climate_orchestrator.coordinator import SmartClimateCoordinator
from tests.conftest import AREA_TEMP_SENSOR, TRV_ENTITY
from tests.ha.helpers import refresh

_TRV_ATTRS = {"hvac_modes": ["off", "heat"]}


def _events_of(events: list, event_type: str) -> list:
    return [e for e in events if e.data["type"] == event_type]


async def _establish_compliance(
    hass: HomeAssistant, entry: MockConfigEntry
) -> tuple[SmartClimateCoordinator, list, list]:
    """Run a cycle (commanding ``off``), then comply; mock the climate services.

    Registers the (succeeding) climate service mocks exactly once and returns
    the ``set_hvac_mode`` calls list — re-registering would orphan any handle
    a test took earlier. The compliance transition itself must not trigger a
    takeover: the old state didn't match the command, so it reads as the
    device applying it.
    """
    set_hvac = async_mock_service(hass, "climate", "set_hvac_mode")
    set_temp = async_mock_service(hass, "climate", "set_temperature")
    await refresh(hass, entry)
    coordinator: SmartClimateCoordinator = entry.runtime_data
    assert coordinator._runtime(TRV_ENTITY).command is not None
    hass.states.async_set(TRV_ENTITY, "off", _TRV_ATTRS)
    await hass.async_block_till_done()
    assert coordinator._runtime(TRV_ENTITY).override_until is None
    return coordinator, set_hvac, set_temp


async def _human_touches_trv(hass: HomeAssistant) -> None:
    hass.states.async_set(TRV_ENTITY, "heat", _TRV_ATTRS)
    await hass.async_block_till_done()


async def test_external_change_starts_override(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Compliant -> deviating means a human: takeover starts, with an event."""
    events = async_capture_events(hass, EVENT_CLIMATE_ORCHESTRATOR)
    coordinator, _, _ = await _establish_compliance(hass, init_integration)

    await _human_touches_trv(hass)
    runtime = coordinator._runtime(TRV_ENTITY)
    assert runtime.override_until is not None
    started = [e for e in events if e.data["type"] == EVENT_TYPE_OVERRIDE_STARTED]
    assert len(started) == 1
    assert started[0].data["entity_id"] == TRV_ENTITY
    assert started[0].data["duration_minutes"] == 60.0


async def test_override_suppresses_writes_and_surfaces_reason(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """While overridden the device gets no writes and reports the reason."""
    coordinator, set_hvac, _ = await _establish_compliance(hass, init_integration)
    await _human_touches_trv(hass)

    set_hvac.clear()
    await refresh(hass, init_integration)
    assert not [c for c in set_hvac if c.data[ATTR_ENTITY_ID] == TRV_ENTITY]
    assert coordinator.last_decisions[TRV_ENTITY].reason == "manual_override"
    attrs = coordinator.device_command_attrs(TRV_ENTITY)
    assert attrs["manual_override"] is True
    assert attrs["manual_override_remaining_min"] > 0
    # The intentional divergence must not arm the watchdog.
    assert coordinator._runtime(TRV_ENTITY).ignored_since is None


async def test_override_expires_and_control_resumes(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Past the deadline the next cycle reasserts the commanded state."""
    events = async_capture_events(hass, EVENT_CLIMATE_ORCHESTRATOR)
    coordinator, set_hvac, _ = await _establish_compliance(hass, init_integration)
    await _human_touches_trv(hass)

    coordinator._runtime(TRV_ENTITY).override_until = time.monotonic() - 1.0
    set_hvac.clear()
    await refresh(hass, init_integration)

    ended = [e for e in events if e.data["type"] == EVENT_TYPE_OVERRIDE_ENDED]
    assert len(ended) == 1
    assert ended[0].data["reason"] == "expired"
    # The device (manually set to heat) is driven back to the commanded off.
    assert [c for c in set_hvac if c.data[ATTR_ENTITY_ID] == TRV_ENTITY]


async def test_orchestrator_interaction_clears_overrides(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """Touching the whole-home entity reasserts control over every device."""
    events = async_capture_events(hass, EVENT_CLIMATE_ORCHESTRATOR)
    coordinator, _, _ = await _establish_compliance(hass, init_integration)
    await _human_touches_trv(hass)
    assert coordinator._runtime(TRV_ENTITY).override_until is not None

    await hass.services.async_call(
        "climate",
        "set_preset_mode",
        {
            ATTR_ENTITY_ID: entity_id_for("climate", init_integration.entry_id),
            "preset_mode": "sleep",
        },
        blocking=True,
    )
    await hass.async_block_till_done()

    assert coordinator._runtime(TRV_ENTITY).override_until is None
    ended = [e for e in events if e.data["type"] == EVENT_TYPE_OVERRIDE_ENDED]
    assert ended and ended[0].data["reason"] == "reasserted"


async def test_frost_protection_punches_through_override(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """A freezing room ends the override and forces heat immediately."""
    events = async_capture_events(hass, EVENT_CLIMATE_ORCHESTRATOR)
    # heat_cool first, via the *real* climate service (the helper's mocks
    # would swallow this call), and before compliance: _apply_and_control
    # clears overrides.
    await hass.services.async_call(
        "climate",
        "set_hvac_mode",
        {
            ATTR_ENTITY_ID: entity_id_for("climate", init_integration.entry_id),
            "hvac_mode": "heat_cool",
        },
        blocking=True,
    )
    coordinator, _, set_temp = await _establish_compliance(hass, init_integration)
    await _human_touches_trv(hass)
    assert coordinator._runtime(TRV_ENTITY).override_until is not None

    hass.states.async_set(AREA_TEMP_SENSOR, "5.0", {"device_class": "temperature"})
    set_temp.clear()
    await refresh(hass, init_integration)

    ended = [e for e in events if e.data["type"] == EVENT_TYPE_OVERRIDE_ENDED]
    assert ended and ended[0].data["reason"] == "frost_protection"
    # The human had already set the TRV to heat, so reconcile skips the
    # (redundant) mode write — the forced-heat evidence is the setpoint write.
    assert [c for c in set_temp if c.data[ATTR_ENTITY_ID] == TRV_ENTITY]
    assert coordinator.last_decisions[TRV_ENTITY].reason == "frost_protection"


async def test_zero_duration_disables_takeover(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """Duration 0 turns the feature off entirely."""
    cid = init_integration.entry_id
    await hass.services.async_call(
        "number",
        "set_value",
        {
            ATTR_ENTITY_ID: entity_id_for("number", f"{cid}_manual_override_duration"),
            "value": 0,
        },
        blocking=True,
    )
    coordinator, _, _ = await _establish_compliance(hass, init_integration)
    await _human_touches_trv(hass)
    assert coordinator._runtime(TRV_ENTITY).override_until is None


async def test_setpoint_change_also_triggers_override(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """A target-setpoint nudge of >= one step counts as a takeover too."""
    await hass.services.async_call(
        "climate",
        "set_hvac_mode",
        {
            ATTR_ENTITY_ID: entity_id_for("climate", init_integration.entry_id),
            "hvac_mode": "heat_cool",
        },
        blocking=True,
    )
    # Mocks only *after* the real orchestrator call above would be swallowed.
    async_mock_service(hass, "climate", "set_hvac_mode")
    async_mock_service(hass, "climate", "set_temperature")
    # The TRV must advertise heat capability before the cycle, or
    # build_command collapses to OFF. Drain the state events *before*
    # refreshing: the detection listener must judge these transitions against
    # the still-current command, not the heat command the refresh builds.
    hass.states.async_set(TRV_ENTITY, "off", _TRV_ATTRS)
    hass.states.async_set(AREA_TEMP_SENSOR, "18.0", {"device_class": "temperature"})
    await hass.async_block_till_done()
    # A cold room: the TRV is commanded to heat toward a target.
    await refresh(hass, init_integration)
    coordinator: SmartClimateCoordinator = init_integration.runtime_data
    command = coordinator._runtime(TRV_ENTITY).command
    assert command is not None and command.target_temp is not None

    # Device complies (mode + setpoint), then a human turns the dial +2 °C.
    hass.states.async_set(
        TRV_ENTITY,
        command.hvac_mode.value,
        {**_TRV_ATTRS, "temperature": command.target_temp, "target_temp_step": 0.5},
    )
    await hass.async_block_till_done()
    assert coordinator._runtime(TRV_ENTITY).override_until is None

    hass.states.async_set(
        TRV_ENTITY,
        command.hvac_mode.value,
        {
            **_TRV_ATTRS,
            "temperature": command.target_temp + 2.0,
            "target_temp_step": 0.5,
        },
    )
    await hass.async_block_till_done()
    assert coordinator._runtime(TRV_ENTITY).override_until is not None


# --- Command-ignored watchdog -------------------------------------------------


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
    await refresh(hass, entry)
    await refresh(hass, entry)
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
    await refresh(hass, init_integration)
    assert registry.async_get_issue(DOMAIN, _IGNORED_ISSUE) is not None

    # The device finally applies the commanded mode -> issue clears.
    hass.states.async_set(TRV_ENTITY, "off")
    await refresh(hass, init_integration)
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
    await refresh(hass, init_integration)
    await refresh(hass, init_integration)

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
    await refresh(hass, init_integration)
    assert registry.async_get_issue(DOMAIN, _IGNORED_ISSUE) is not None

    hass.states.async_set(TRV_ENTITY, STATE_UNAVAILABLE)
    await refresh(hass, init_integration)
    assert registry.async_get_issue(DOMAIN, _IGNORED_ISSUE) is None
    assert coordinator._runtime(TRV_ENTITY).ignored_since is None


async def test_watchdog_events_fire_on_both_edges(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
) -> None:
    """The watchdog announces non-compliance and recovery exactly once each."""
    async_mock_service(hass, "climate", "set_hvac_mode")
    async_mock_service(hass, "climate", "set_temperature")
    events = async_capture_events(hass, EVENT_CLIMATE_ORCHESTRATOR)
    coordinator: SmartClimateCoordinator = init_integration.runtime_data
    await refresh(hass, init_integration)
    await refresh(hass, init_integration)

    coordinator._runtime(TRV_ENTITY).ignored_since = time.monotonic() - 999.0
    await refresh(hass, init_integration)
    await refresh(hass, init_integration)
    started = _events_of(events, EVENT_TYPE_IGNORING_STARTED)
    assert len(started) == 1  # edge, not per cycle
    assert started[0].data["entity_id"] == TRV_ENTITY

    hass.states.async_set(TRV_ENTITY, "off")  # device finally complies
    await refresh(hass, init_integration)
    ended = _events_of(events, EVENT_TYPE_IGNORING_ENDED)
    assert len(ended) == 1


async def test_loud_failures_fire_no_watchdog_events(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
) -> None:
    """Failing service calls never produce watchdog events."""

    async def _device_rejects(call: ServiceCall) -> None:
        raise HomeAssistantError

    hass.services.async_register("climate", "set_hvac_mode", _device_rejects)
    hass.services.async_register("climate", "set_temperature", _device_rejects)
    events = async_capture_events(hass, EVENT_CLIMATE_ORCHESTRATOR)
    await refresh(hass, init_integration)
    await refresh(hass, init_integration)
    assert not _events_of(events, EVENT_TYPE_IGNORING_STARTED)
