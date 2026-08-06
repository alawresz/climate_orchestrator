"""AC condensate-drain protection: monitor timing and end-to-end gating."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
    async_fire_time_changed,
    async_mock_service,
)

from custom_components.climate_orchestrator.const import (
    AC_DRAIN_GRACE_DEFAULT,
    CONF_AC_DRAIN_SENSOR,
    CONF_ACS,
    CONF_TRVS,
    DEFAULT_TITLE,
    DOMAIN,
    EVENT_CLIMATE_ORCHESTRATOR,
    EVENT_TYPE_DRAIN_PAUSE_ENDED,
    EVENT_TYPE_DRAIN_PAUSE_STARTED,
)
from custom_components.climate_orchestrator.control.hysteresis import Demand
from custom_components.climate_orchestrator.coordinator import SmartClimateCoordinator
from custom_components.climate_orchestrator.drain import DrainMonitor
from custom_components.climate_orchestrator.settings import resolve_settings
from tests.conftest import AC_ENTITY, AREA_TEMP_SENSOR, TRV_ENTITY
from tests.ha.helpers import refresh, set_desired_preset

_DRAIN = "binary_sensor.ac_condensate_tank_full"
_GRACE = 600.0


def _notifications(hass: HomeAssistant) -> dict[str, Any]:
    """The persistent (bell-panel) notifications by notification_id."""
    return hass.data.get("persistent_notification", {})


def _events_of(events: list, event_type: str) -> list:
    return [e for e in events if e.data["type"] == event_type]


async def test_monitor_blocks_after_grace_and_reruns_control(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Active past the grace window blocks, and the one-shot timer re-runs control.

    Without the timer a freshly-tripped sensor would only be caught by the next
    keepalive — up to a minute after the grace window actually ended.
    """
    rechecks: list[bool] = []
    monitor = DrainMonitor(hass, lambda: rechecks.append(True))

    # Freshly active: inside the grace window, not blocking yet, timer armed.
    assert monitor.blocks(active=True, grace_seconds=_GRACE) is False
    assert not rechecks

    freezer.tick(timedelta(seconds=_GRACE + 1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert rechecks  # control was re-run by the timer, not a keepalive
    assert monitor.blocks(active=True, grace_seconds=_GRACE) is True


async def test_monitor_clears_immediately_when_inactive(hass: HomeAssistant) -> None:
    """Emptying the tank resets the timer at once, so cooling can resume."""
    monitor = DrainMonitor(hass, lambda: None)
    monitor.blocks(active=True, grace_seconds=0.0)
    assert monitor.blocks(active=True, grace_seconds=0.0) is True
    # Sensor clears -> no longer blocking, and a later trip starts a fresh grace.
    assert monitor.blocks(active=False, grace_seconds=_GRACE) is False
    assert monitor.blocks(active=True, grace_seconds=_GRACE) is False
    monitor.shutdown()  # cancel the grace timer the last call armed


async def test_monitor_zero_grace_blocks_immediately(hass: HomeAssistant) -> None:
    """A zero grace window stops the AC the instant the sensor trips."""
    monitor = DrainMonitor(hass, lambda: None)
    assert monitor.blocks(active=True, grace_seconds=0.0) is True


async def test_drain_entities_absent_without_a_configured_sensor(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """No drain sensor -> no toggle/grace entities, and the gate is inert.

    The settings still resolve (with defaults) so ``RuntimeSettings`` is whole.
    """
    coordinator: SmartClimateCoordinator = init_integration.runtime_data
    assert coordinator.ac_drain_protection_available is False
    registry = er.async_get(hass)
    cid = init_integration.entry_id
    assert (
        registry.async_get_entity_id("switch", DOMAIN, f"{cid}_ac_drain_protection")
        is None
    )
    assert (
        registry.async_get_entity_id("number", DOMAIN, f"{cid}_ac_drain_grace") is None
    )

    settings = resolve_settings(hass, cid)
    assert settings.ac_drain_grace == AC_DRAIN_GRACE_DEFAULT
    assert settings.ac_drain_protection is True


async def test_full_tank_idles_the_ac_and_resumes_when_cleared(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    living_area: str,
    register_entity_in_area: Callable[[str, str | None], str],
    entity_id_for: Callable[[str, str], str],
) -> None:
    """End-to-end: a full tank holds the AC off after the grace, then resumes."""
    register_entity_in_area(TRV_ENTITY, living_area)
    register_entity_in_area(AC_ENTITY, living_area)
    hass.states.async_set(TRV_ENTITY, "off", {"hvac_modes": ["off", "heat"]})
    hass.states.async_set(
        AC_ENTITY,
        "off",
        {
            "hvac_modes": ["off", "cool"],
            "current_temperature": 28.0,
            "temperature": 24.0,
        },
    )
    hass.states.async_set(_DRAIN, "off", {"device_class": "moisture"})
    hass.states.async_set(AREA_TEMP_SENSOR, "28.0", {"device_class": "temperature"})

    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_TITLE,
        data={
            CONF_TRVS: [TRV_ENTITY],
            CONF_ACS: [AC_ENTITY],
            CONF_AC_DRAIN_SENSOR: _DRAIN,
        },
        entry_id="sc_drain",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Turn the system on through the real service *before* the climate services
    # are replaced by recorders: a mocked service would swallow the call. Being
    # a real entity it then stays on, so no cycle has to re-assert it.
    climate_id = entity_id_for("climate", entry.entry_id)
    await set_desired_preset(hass, climate_id, "heat_cool")
    async_mock_service(hass, "climate", "set_hvac_mode")
    async_mock_service(hass, "climate", "set_temperature")

    coordinator: SmartClimateCoordinator = entry.runtime_data
    assert coordinator.ac_drain_protection_available is True
    events = async_capture_events(hass, EVENT_CLIMATE_ORCHESTRATOR)
    notification_id = f"climate_orchestrator_{entry.entry_id}_ac_drain_full"

    async def _cycle() -> None:
        await refresh(hass, entry)

    # Baseline: a hot room with the tank empty -> the AC cools.
    await _cycle()
    assert coordinator.last_decisions[AC_ENTITY].demand is Demand.COOL

    # Tank fills: still cooling while inside the grace window (no event yet).
    hass.states.async_set(_DRAIN, "on", {"device_class": "moisture"})
    await _cycle()
    assert coordinator.last_decisions[AC_ENTITY].demand is Demand.COOL
    assert not _events_of(events, EVENT_TYPE_DRAIN_PAUSE_STARTED)

    # Past the grace window: the AC is held off with the drain_full reason,
    # and a single self-clearing notification + bus event announce it.
    freezer.tick(timedelta(minutes=AC_DRAIN_GRACE_DEFAULT + 1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    await _cycle()
    assert coordinator.last_decisions[AC_ENTITY].demand is Demand.IDLE
    assert coordinator.last_decisions[AC_ENTITY].reason == "drain_full"
    assert coordinator.hvac_action_reason() == "drain_full"
    started = _events_of(events, EVENT_TYPE_DRAIN_PAUSE_STARTED)
    assert len(started) == 1
    assert AC_ENTITY in started[0].data["entities"]
    assert notification_id in _notifications(hass)

    # Still paused next cycle: edge-triggered, so no duplicate event.
    await _cycle()
    assert len(_events_of(events, EVENT_TYPE_DRAIN_PAUSE_STARTED)) == 1

    # Tank emptied: cooling resumes, the pause-ended event fires, notice clears.
    hass.states.async_set(_DRAIN, "off", {"device_class": "moisture"})
    await _cycle()
    assert coordinator.last_decisions[AC_ENTITY].demand is Demand.COOL
    assert len(_events_of(events, EVENT_TYPE_DRAIN_PAUSE_ENDED)) == 1
    assert notification_id not in _notifications(hass)


async def test_unavailable_drain_sensor_raises_repair_and_clears(
    hass: HomeAssistant,
    living_area: str,
    register_entity_in_area: Callable[[str, str | None], str],
) -> None:
    """A configured-but-unavailable drain sensor (protection on) is flagged.

    Protection fails open when it can't read the sensor, so it's silently
    inactive — surfaced like the other "configured source missing" repairs.
    (The shared warm-up gate that holds these back during ``initializing`` is
    covered by the status tests; here a room sensor is present, so the entry
    settles immediately.)
    """
    register_entity_in_area(TRV_ENTITY, living_area)
    register_entity_in_area(AC_ENTITY, living_area)
    hass.states.async_set(TRV_ENTITY, "off", {"hvac_modes": ["off", "heat"]})
    hass.states.async_set(AC_ENTITY, "off", {"hvac_modes": ["off", "cool"]})
    hass.states.async_set(_DRAIN, STATE_UNAVAILABLE, {"device_class": "moisture"})

    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_TITLE,
        data={
            CONF_TRVS: [TRV_ENTITY],
            CONF_ACS: [AC_ENTITY],
            CONF_AC_DRAIN_SENSOR: _DRAIN,
        },
        entry_id="sc_drain_unavail",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    registry = ir.async_get(hass)

    # Protection on + configured sensor unavailable -> the repair fires.
    await refresh(hass, entry)
    assert registry.async_get_issue(DOMAIN, "ac_drain_sensor_unavailable") is not None

    # Sensor reports again -> protection can run, notice clears.
    hass.states.async_set(_DRAIN, "off", {"device_class": "moisture"})
    await refresh(hass, entry)
    assert registry.async_get_issue(DOMAIN, "ac_drain_sensor_unavailable") is None
