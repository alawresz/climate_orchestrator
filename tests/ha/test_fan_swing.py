"""Tests for AC fan/swing passthrough on the whole-home entity."""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.components.climate import (
    ATTR_FAN_MODE,
    ATTR_SWING_MODE,
    SERVICE_SET_FAN_MODE,
    SERVICE_SET_SWING_MODE,
    ClimateEntityFeature,
)
from homeassistant.components.climate import (
    DOMAIN as CLIMATE_DOMAIN,
)
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_component import EntityComponent
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.climate_orchestrator.coordinator import SmartClimateCoordinator
from tests.conftest import AC_ENTITY

_AC_ATTRS = {
    "hvac_modes": ["off", "cool"],
    "fan_modes": ["auto", "low", "high"],
    "swing_modes": ["off", "vertical"],
    "fan_mode": "auto",
    "swing_mode": "off",
}


async def _advertise_ac_modes(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    hass.states.async_set(AC_ENTITY, "cool", _AC_ATTRS)
    coordinator: SmartClimateCoordinator = init_integration.runtime_data
    await coordinator.async_refresh()
    await hass.async_block_till_done()


async def test_fan_and_swing_modes_exposed(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """When the AC advertises fan/swing, the whole-home entity surfaces them."""
    await _advertise_ac_modes(hass, init_integration)
    state = hass.states.get(entity_id_for("climate", init_integration.entry_id))
    assert state.attributes["fan_modes"] == ["auto", "low", "high"]
    assert state.attributes["swing_modes"] == ["off", "vertical"]
    features = state.attributes["supported_features"]
    assert features & ClimateEntityFeature.FAN_MODE
    assert features & ClimateEntityFeature.SWING_MODE


async def test_fan_mode_forwarded_to_ac(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """Setting the fan mode forwards it to the AC that supports it."""
    await _advertise_ac_modes(hass, init_integration)
    climate_id = entity_id_for("climate", init_integration.entry_id)
    calls = async_mock_service(hass, CLIMATE_DOMAIN, SERVICE_SET_FAN_MODE)

    component: EntityComponent = hass.data[CLIMATE_DOMAIN]
    entity = component.get_entity(climate_id)
    assert entity is not None
    await entity.async_set_fan_mode("low")

    assert any(
        c.data[ATTR_ENTITY_ID] == AC_ENTITY and c.data[ATTR_FAN_MODE] == "low"
        for c in calls
    )
    assert hass.states.get(climate_id).attributes["fan_mode"] == "low"


async def test_swing_mode_forwarded_to_ac(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """Setting the swing mode forwards it to the AC and sticks for display."""
    await _advertise_ac_modes(hass, init_integration)
    climate_id = entity_id_for("climate", init_integration.entry_id)
    calls = async_mock_service(hass, CLIMATE_DOMAIN, SERVICE_SET_SWING_MODE)

    component: EntityComponent = hass.data[CLIMATE_DOMAIN]
    entity = component.get_entity(climate_id)
    assert entity is not None
    await entity.async_set_swing_mode("vertical")

    assert any(
        c.data[ATTR_ENTITY_ID] == AC_ENTITY and c.data[ATTR_SWING_MODE] == "vertical"
        for c in calls
    )
    # The last set value sticks (rather than re-reading the first AC).
    assert hass.states.get(climate_id).attributes["swing_mode"] == "vertical"
