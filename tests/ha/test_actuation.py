"""Tests for the coordinator driving devices (actuation)."""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.components.climate import ATTR_HVAC_MODE
from homeassistant.const import ATTR_ENTITY_ID, ATTR_TEMPERATURE, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.climate_orchestrator.coordinator import SmartClimateCoordinator
from tests.conftest import AC_ENTITY, AREA_TEMP_SENSOR, TRV_ENTITY
from tests.ha.helpers import TRV_ATTRS, set_desired_preset


async def test_heating_demand_commands_the_trv(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """A cold room with the system on commands the TRV to heat."""
    set_hvac = async_mock_service(hass, "climate", "set_hvac_mode")
    async_mock_service(hass, "climate", "set_temperature")
    climate_id = entity_id_for("climate", init_integration.entry_id)

    hass.states.async_set(TRV_ENTITY, "off", TRV_ATTRS)
    hass.states.async_set(AREA_TEMP_SENSOR, "19.0")
    set_desired_preset(hass, climate_id, "heat_cool")

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
    hass.states.async_set(TRV_ENTITY, "heat", {**TRV_ATTRS, "temperature": 21.0})
    hass.states.async_set(AREA_TEMP_SENSOR, "19.0")
    set_desired_preset(hass, climate_id, "heat_cool")

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
    hass.states.async_set(TRV_ENTITY, "off", TRV_ATTRS)
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
    set_desired_preset(hass, climate_id, "heat_cool")

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
    set_desired_preset(hass, climate_id, "heat_cool")

    coordinator: SmartClimateCoordinator = init_integration.runtime_data
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert TRV_ENTITY in coordinator.last_decisions
    assert AC_ENTITY in coordinator.last_decisions
    assert hass.states.get(climate_id).state != STATE_UNAVAILABLE


async def test_home_average_trigger_switch_wires_into_control(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """Switch off -> a cold home average no longer starts a satisfied room."""
    set_hvac = async_mock_service(hass, "climate", "set_hvac_mode")
    async_mock_service(hass, "climate", "set_temperature")
    cid = init_integration.entry_id

    # A whole-home override makes the home average (19.0) differ from the
    # room's own reading (22.0, mid-band) in a one-room test home.
    hass.states.async_set(
        "sensor.whole_home_temp", "19.0", {"device_class": "temperature"}
    )
    hass.config_entries.async_update_entry(
        init_integration,
        options={"home_temperature_sensor": "sensor.whole_home_temp"},
    )
    await hass.async_block_till_done()
    coordinator: SmartClimateCoordinator = init_integration.runtime_data
    climate_id = entity_id_for("climate", cid)

    hass.states.async_set(TRV_ENTITY, "off", TRV_ATTRS)
    hass.states.async_set(AREA_TEMP_SENSOR, "22.0")
    set_desired_preset(hass, climate_id, "heat_cool")

    await coordinator.async_refresh()
    await hass.async_block_till_done()
    # Trigger on (default): the cold home average pulls the room in.
    assert any(
        c.data[ATTR_ENTITY_ID] == TRV_ENTITY and c.data[ATTR_HVAC_MODE] == "heat"
        for c in set_hvac
    )

    switch = entity_id_for("switch", f"{cid}_home_average_trigger")
    await hass.services.async_call(
        "switch", "turn_off", {ATTR_ENTITY_ID: switch}, blocking=True
    )
    await hass.async_block_till_done()
    hass.states.async_set(TRV_ENTITY, "off", TRV_ATTRS)
    set_hvac.clear()

    await coordinator.async_refresh()
    await hass.async_block_till_done()
    # Independent rooms: local 22.0 is content, the cold home average is ignored.
    assert not [
        c
        for c in set_hvac
        if c.data[ATTR_ENTITY_ID] == TRV_ENTITY and c.data[ATTR_HVAC_MODE] == "heat"
    ]


async def test_command_failures_log_once_per_outage(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A failing device warns once, stays quiet, and logs once on recovery."""
    climate_id = entity_id_for("climate", init_integration.entry_id)
    # Deterministic outage: the climate services exist but reject every command.
    # (Overrides the real entity services the climate component registered, and
    # avoids racing setup's first control cycle, whose ServiceNotFound warning
    # lands in caplog's setup phase, not the call phase counted below.)
    failing = True

    async def _device_rejects(call: ServiceCall) -> None:
        if failing:
            raise HomeAssistantError

    hass.services.async_register("climate", "set_hvac_mode", _device_rejects)
    hass.services.async_register("climate", "set_temperature", _device_rejects)
    hass.states.async_set(TRV_ENTITY, "off", TRV_ATTRS)
    hass.states.async_set(AREA_TEMP_SENSOR, "19.0")
    coordinator: SmartClimateCoordinator = init_integration.runtime_data
    # Setup's very first cycle already tripped the latch (no climate services
    # existed yet, in caplog's setup phase); reset it so the outage below
    # starts from a healthy device.
    coordinator._runtime(TRV_ENTITY).command_failing = False
    caplog.clear()

    async def _cycle() -> None:
        # Each refresh makes the real climate entity rewrite its state, wiping
        # the faked desired mode — re-fake it before every cycle.
        set_desired_preset(hass, climate_id)
        await coordinator.async_refresh()
        await hass.async_block_till_done()

    def _warnings() -> int:
        return sum(
            1
            for r in caplog.records
            if "failed to command" in r.getMessage() and TRV_ENTITY in r.getMessage()
        )

    await _cycle()
    assert _warnings() == 1

    await _cycle()
    assert _warnings() == 1  # still just the one warning while it stays down

    failing = False
    await _cycle()
    assert _warnings() == 1
    assert any(
        "accepting commands again" in r.getMessage() and TRV_ENTITY in r.getMessage()
        for r in caplog.records
    )


async def test_dead_window_timer_areas_are_pruned(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Window timers for areas no longer backing a device are evicted.

    A registry area change doesn't reload the entry, so the per-area dict
    must self-clean each cycle instead of holding dead keys forever.
    """
    coordinator: SmartClimateCoordinator = init_integration.runtime_data
    coordinator._window_open_since["ghost_area"] = 123.0
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert "ghost_area" not in coordinator._window_open_since
