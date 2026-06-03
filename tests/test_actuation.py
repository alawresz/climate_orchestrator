"""Tests for the coordinator driving devices (actuation)."""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.components.climate import ATTR_HVAC_MODE
from homeassistant.const import ATTR_ENTITY_ID, ATTR_TEMPERATURE, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant, ServiceCall
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.climate_orchestrator.coordinator import SmartClimateCoordinator
from tests.conftest import AC_ENTITY, AREA_TEMP_SENSOR, TRV_ENTITY

_TRV_ATTRS = {
    "hvac_modes": ["off", "heat"],
    "min_temp": 7.0,
    "max_temp": 35.0,
    "target_temp_step": 0.5,
}


def _set_desired(
    hass: HomeAssistant, climate_id: str, mode: str, *, target: float = 22.5
) -> None:
    """Fake the whole-home entity's desired state read by the coordinator."""
    hass.states.async_set(
        climate_id, mode, {"temperature": target, "preset_mode": "home"}
    )


async def test_heating_demand_commands_the_trv(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """A cold room with the system on commands the TRV to heat."""
    set_hvac = async_mock_service(hass, "climate", "set_hvac_mode")
    async_mock_service(hass, "climate", "set_temperature")
    climate_id = entity_id_for("climate", init_integration.entry_id)

    hass.states.async_set(TRV_ENTITY, "off", _TRV_ATTRS)
    hass.states.async_set(AREA_TEMP_SENSOR, "19.0")
    _set_desired(hass, climate_id, "heat_cool")

    coordinator: SmartClimateCoordinator = init_integration.runtime_data
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert any(
        c.data[ATTR_ENTITY_ID] == TRV_ENTITY and c.data[ATTR_HVAC_MODE] == "heat"
        for c in set_hvac
    )


async def test_no_redundant_writes_when_already_satisfied(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """If the TRV is already heating at the target, nothing is re-sent."""
    set_hvac = async_mock_service(hass, "climate", "set_hvac_mode")
    set_temp = async_mock_service(hass, "climate", "set_temperature")
    climate_id = entity_id_for("climate", init_integration.entry_id)

    # Already at the heat target (heat_edge 20.5 + tolerance 0.3 -> 20.8 -> 21.0).
    hass.states.async_set(TRV_ENTITY, "heat", {**_TRV_ATTRS, "temperature": 21.0})
    hass.states.async_set(AREA_TEMP_SENSOR, "19.0")
    _set_desired(hass, climate_id, "heat_cool")

    coordinator: SmartClimateCoordinator = init_integration.runtime_data
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert not [c for c in set_hvac if c.data[ATTR_ENTITY_ID] == TRV_ENTITY]
    assert not [c for c in set_temp if c.data[ATTR_ENTITY_ID] == TRV_ENTITY]


async def test_ac_setpoint_is_throttled_between_cycles(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """A second cooling cycle within the min interval doesn't re-write the AC
    setpoint, even though the proportional anchor moved it by >= one step."""
    writes: list[float] = []

    async def _set_temp(call: ServiceCall) -> None:
        eid = call.data[ATTR_ENTITY_ID]
        temp = call.data[ATTR_TEMPERATURE]
        if eid == AC_ENTITY:
            writes.append(temp)
        st = hass.states.get(eid)
        hass.states.async_set(eid, st.state, {**st.attributes, "temperature": temp})

    async def _set_mode(call: ServiceCall) -> None:
        eid = call.data[ATTR_ENTITY_ID]
        st = hass.states.get(eid)
        hass.states.async_set(eid, call.data[ATTR_HVAC_MODE], st.attributes)

    # Stateful mocks so the device reflects what we write (reconcile needs that).
    hass.services.async_register("climate", "set_temperature", _set_temp)
    hass.services.async_register("climate", "set_hvac_mode", _set_mode)

    climate_id = entity_id_for("climate", init_integration.entry_id)
    hass.states.async_set(TRV_ENTITY, "off", _TRV_ATTRS)
    hass.states.async_set(
        AC_ENTITY,
        "off",
        {
            "hvac_modes": ["off", "cool"],
            "current_temperature": 28.0,
            "temperature": 24.0,
        },
    )
    hass.states.async_set(AREA_TEMP_SENSOR, "28.0", {"device_class": "temperature"})
    _set_desired(hass, climate_id, "heat_cool")

    coordinator: SmartClimateCoordinator = init_integration.runtime_data

    # Cycle 1: AC engages cooling -> one setpoint write.
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert len(writes) == 1

    # The AC's own reading drifts (shifts the anchored target by >= a step), but
    # we're well within the min interval -> the held setpoint suppresses a write.
    st = hass.states.get(AC_ENTITY)
    hass.states.async_set(
        AC_ENTITY, st.state, {**st.attributes, "current_temperature": 24.0}
    )
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert len(writes) == 1  # still just the first write


async def test_unavailable_device_does_not_break_the_cycle(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """An offline TRV is excluded; the cycle still completes for the rest."""
    async_mock_service(hass, "climate", "set_hvac_mode")
    async_mock_service(hass, "climate", "set_temperature")
    climate_id = entity_id_for("climate", init_integration.entry_id)

    hass.states.async_set(TRV_ENTITY, STATE_UNAVAILABLE)
    _set_desired(hass, climate_id, "heat_cool")

    coordinator: SmartClimateCoordinator = init_integration.runtime_data
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert TRV_ENTITY in coordinator.last_decisions
    assert AC_ENTITY in coordinator.last_decisions
    assert hass.states.get(climate_id).state != STATE_UNAVAILABLE
