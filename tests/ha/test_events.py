"""Tests for the bus events and the self-clearing bell notifications."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homeassistant.const import ATTR_ENTITY_ID, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
)

from custom_components.climate_orchestrator.const import (
    EVENT_CLIMATE_ORCHESTRATOR,
    EVENT_TYPE_FROST_ENDED,
    EVENT_TYPE_FROST_STARTED,
    EVENT_TYPE_STATUS_CHANGED,
    EVENT_TYPE_WINDOW_PAUSE_STARTED,
)
from custom_components.climate_orchestrator.coordinator import SmartClimateCoordinator
from tests.conftest import AREA_TEMP_SENSOR, TRV_ENTITY


def _notifications(hass: HomeAssistant) -> dict[str, Any]:
    """The persistent (bell-panel) notifications by notification_id."""
    return hass.data.get("persistent_notification", {})


def _events_of(events: list, event_type: str) -> list:
    return [e for e in events if e.data["type"] == event_type]


async def _refresh(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    coordinator: SmartClimateCoordinator = entry.runtime_data
    await coordinator.async_refresh()
    await hass.async_block_till_done()


async def _drive_frost(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """Freeze the living room with a heat-capable TRV in heat_cool mode."""
    await hass.services.async_call(
        "climate",
        "set_hvac_mode",
        {
            ATTR_ENTITY_ID: entity_id_for("climate", entry.entry_id),
            "hvac_mode": "heat_cool",
        },
        blocking=True,
    )
    hass.states.async_set(AREA_TEMP_SENSOR, "5.0", {"device_class": "temperature"})
    hass.states.async_set(TRV_ENTITY, "heat", {"hvac_modes": ["off", "heat"]})
    await _refresh(hass, entry)


async def test_frost_events_and_notification(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """Frost engaging fires one event and one bell notification; both clear."""
    events = async_capture_events(hass, EVENT_CLIMATE_ORCHESTRATOR)
    notification_id = (
        f"climate_orchestrator_{init_integration.entry_id}_frost_protection"
    )

    await _drive_frost(hass, init_integration, entity_id_for)
    started = _events_of(events, EVENT_TYPE_FROST_STARTED)
    assert len(started) == 1
    assert TRV_ENTITY in started[0].data["entities"]
    assert notification_id in _notifications(hass)

    # Still frosty next cycle: edge-triggered, so no duplicate.
    await _refresh(hass, init_integration)
    assert len(_events_of(events, EVENT_TYPE_FROST_STARTED)) == 1

    hass.states.async_set(AREA_TEMP_SENSOR, "21.0", {"device_class": "temperature"})
    await _refresh(hass, init_integration)
    assert len(_events_of(events, EVENT_TYPE_FROST_ENDED)) == 1
    assert notification_id not in _notifications(hass)


async def test_notifications_switch_gates_the_notification_not_the_event(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """With the switch off, automations still get events; the bell stays quiet."""
    cid = init_integration.entry_id
    await hass.services.async_call(
        "switch",
        "turn_off",
        {ATTR_ENTITY_ID: entity_id_for("switch", f"{cid}_event_notifications")},
        blocking=True,
    )
    events = async_capture_events(hass, EVENT_CLIMATE_ORCHESTRATOR)

    await _drive_frost(hass, init_integration, entity_id_for)
    assert len(_events_of(events, EVENT_TYPE_FROST_STARTED)) == 1
    assert f"climate_orchestrator_{cid}_frost_protection" not in _notifications(hass)


async def test_window_pause_event_carries_the_device(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    living_area: str,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """A window pausing a device fires per-device events with the area."""
    cid = init_integration.entry_id
    # No grace delay, so the pause starts on the very next cycle.
    await hass.services.async_call(
        "number",
        "set_value",
        {
            ATTR_ENTITY_ID: entity_id_for("number", f"{cid}_window_open_delay"),
            "value": 0,
        },
        blocking=True,
    )
    registry = er.async_get(hass)
    window = registry.async_get_or_create(
        "binary_sensor",
        "test",
        "u_window",
        suggested_object_id="living_window",
        original_device_class="window",
    )
    registry.async_update_entity(window.entity_id, area_id=living_area)
    hass.states.async_set(window.entity_id, "off")
    await _refresh(hass, init_integration)

    events = async_capture_events(hass, EVENT_CLIMATE_ORCHESTRATOR)
    hass.states.async_set(window.entity_id, "on")
    await _refresh(hass, init_integration)

    started = _events_of(events, EVENT_TYPE_WINDOW_PAUSE_STARTED)
    assert {e.data["entity_id"] for e in started} >= {TRV_ENTITY}
    assert all(e.data["area_id"] == living_area for e in started)


async def test_status_change_event_and_degraded_notification(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
) -> None:
    """ok -> degraded fires an event + notification; recovery clears both."""
    events = async_capture_events(hass, EVENT_CLIMATE_ORCHESTRATOR)
    notification_id = f"climate_orchestrator_{init_integration.entry_id}_degraded"

    hass.states.async_set(TRV_ENTITY, STATE_UNAVAILABLE)
    await _refresh(hass, init_integration)
    changed = _events_of(events, EVENT_TYPE_STATUS_CHANGED)
    assert len(changed) == 1
    assert changed[0].data["from"] == "ok"
    assert changed[0].data["to"] == "degraded"
    assert TRV_ENTITY in changed[0].data["unavailable_devices"]
    assert notification_id in _notifications(hass)

    hass.states.async_set(TRV_ENTITY, "heat")
    await _refresh(hass, init_integration)
    changed = _events_of(events, EVENT_TYPE_STATUS_CHANGED)
    assert len(changed) == 2
    assert changed[1].data["to"] == "ok"
    assert notification_id not in _notifications(hass)
