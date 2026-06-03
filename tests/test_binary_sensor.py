"""Tests for the degraded-operation binary sensor."""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.climate_orchestrator.coordinator import SmartClimateCoordinator
from tests.conftest import TRV_ENTITY


async def test_degraded_off_when_all_available(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """No degraded state while every device is available."""
    degraded = entity_id_for("binary_sensor", f"{init_integration.entry_id}_degraded")
    state = hass.states.get(degraded)
    assert state is not None
    assert state.state == "off"


async def test_degraded_on_lists_unavailable_devices(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """An unavailable device turns the sensor on and is listed in attributes."""
    degraded = entity_id_for("binary_sensor", f"{init_integration.entry_id}_degraded")
    hass.states.async_set(TRV_ENTITY, STATE_UNAVAILABLE)
    coordinator: SmartClimateCoordinator = init_integration.runtime_data
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    state = hass.states.get(degraded)
    assert state.state == "on"
    assert TRV_ENTITY in state.attributes["unavailable_devices"]
