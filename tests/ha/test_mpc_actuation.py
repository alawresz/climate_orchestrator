"""Tests for MPC/offset calibration driving a TRV's valve number."""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.climate_orchestrator.control.hysteresis import Demand
from custom_components.climate_orchestrator.control.mpc.controller import MpcController
from custom_components.climate_orchestrator.coordinator import SmartClimateCoordinator
from tests.conftest import AC_ENTITY, AREA_TEMP_SENSOR, TRV_ENTITY

VALVE_NUMBER = "number.trv_1_valve_opening_degree"
CALIBRATION_NUMBER = "number.trv_1_local_temperature_calibration"


async def _setup_with_valve(
    hass: HomeAssistant, config_entry: MockConfigEntry, area_id: str
) -> None:
    """Set up the integration with a TRV that has a valve-opening number."""
    config_entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers={("climate_orchestrator_test", "trv1")},
    )
    registry = er.async_get(hass)
    climate = registry.async_get_or_create(
        "climate", "test", "u_trv1", suggested_object_id="trv_1", device_id=device.id
    )
    registry.async_update_entity(climate.entity_id, area_id=area_id)
    registry.async_get_or_create(
        "number",
        "test",
        "u_valve",
        suggested_object_id="trv_1_valve_opening_degree",
        device_id=device.id,
    )
    hass.states.async_set(
        TRV_ENTITY,
        "heat",
        {
            "hvac_modes": ["off", "heat"],
            "current_temperature": 18.0,
            "temperature": 21.0,
        },
    )
    hass.states.async_set(AC_ENTITY, "off")
    hass.states.async_set(VALVE_NUMBER, "0")
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()


async def _engage_mpc_heating(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
) -> SmartClimateCoordinator:
    """Switch to MPC, then turn the system on into a cold room and recompute."""
    cid = config_entry.entry_id
    await hass.services.async_call(
        "select",
        "select_option",
        {
            ATTR_ENTITY_ID: entity_id_for("select", f"{cid}_calibration_mode"),
            "option": "mpc",
        },
        blocking=True,
    )
    hass.states.async_set(
        entity_id_for("climate", cid),
        "heat_cool",
        {"temperature": 22.5, "preset_mode": "home"},
    )
    hass.states.async_set(AREA_TEMP_SENSOR, "17.0")
    coordinator: SmartClimateCoordinator = config_entry.runtime_data
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    return coordinator


async def test_mpc_mode_writes_valve_number(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    living_area: str,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """In MPC mode a heating TRV gets its valve opening written."""
    await _setup_with_valve(hass, config_entry, living_area)
    set_value = async_mock_service(hass, "number", "set_value")
    await _engage_mpc_heating(hass, config_entry, entity_id_for)
    assert any(call.data[ATTR_ENTITY_ID] == VALVE_NUMBER for call in set_value)


async def test_mpc_closes_valve_when_not_heating(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    living_area: str,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """In MPC mode a non-heating TRV is driven fully shut (valve -> 0)."""
    await _setup_with_valve(hass, config_entry, living_area)
    # Pretend the valve was left open from an earlier heating run.
    hass.states.async_set(VALVE_NUMBER, "80")
    set_value = async_mock_service(hass, "number", "set_value")

    cid = config_entry.entry_id
    await hass.services.async_call(
        "select",
        "select_option",
        {
            ATTR_ENTITY_ID: entity_id_for("select", f"{cid}_calibration_mode"),
            "option": "mpc",
        },
        blocking=True,
    )
    # A warm room -> the heater idles (it can't cool), so the valve must close.
    hass.states.async_set(
        entity_id_for("climate", cid),
        "heat_cool",
        {"temperature": 22.5, "preset_mode": "home"},
    )
    hass.states.async_set(AREA_TEMP_SENSOR, "25.0")
    coordinator: SmartClimateCoordinator = config_entry.runtime_data
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    written = [
        c.data["value"] for c in set_value if c.data[ATTR_ENTITY_ID] == VALVE_NUMBER
    ]
    assert 0.0 in written


async def test_mpc_diagnostic_sensors_reflect_learned_state(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    living_area: str,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """Once a controller exists, the gain sensor reads a number and status moves."""
    await _setup_with_valve(hass, config_entry, living_area)
    async_mock_service(hass, "number", "set_value")
    await _engage_mpc_heating(hass, config_entry, entity_id_for)

    cid = config_entry.entry_id
    gain = hass.states.get(
        entity_id_for("sensor", f"{cid}_{TRV_ENTITY}_mpc_heating_gain")
    )
    status = hass.states.get(
        entity_id_for("sensor", f"{cid}_{TRV_ENTITY}_mpc_learning_status")
    )
    assert gain is not None and float(gain.state) >= 0.0
    assert status.state in ("learning", "ready")


async def test_mpc_state_is_persisted(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    living_area: str,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """A controller is created and its state is serialisable for persistence."""
    await _setup_with_valve(hass, config_entry, living_area)
    async_mock_service(hass, "number", "set_value")
    coordinator = await _engage_mpc_heating(hass, config_entry, entity_id_for)

    persisted = coordinator._mpc_persist_data()
    assert TRV_ENTITY in persisted
    assert "gain" in persisted[TRV_ENTITY]


async def test_offset_mode_writes_calibration_number(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    living_area: str,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """In offset mode a heating TRV gets its local-calibration number written.

    The offset feeds the TRV the room temperature: ``area - TRV's own reading``.
    """
    config_entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers={("climate_orchestrator_test", "trv1")},
    )
    registry = er.async_get(hass)
    climate = registry.async_get_or_create(
        "climate", "test", "u_trv1", suggested_object_id="trv_1", device_id=device.id
    )
    registry.async_update_entity(climate.entity_id, area_id=living_area)
    registry.async_get_or_create(
        "number",
        "test",
        "u_calib",
        suggested_object_id="trv_1_local_temperature_calibration",
        device_id=device.id,
    )
    hass.states.async_set(
        TRV_ENTITY,
        "heat",
        {"hvac_modes": ["off", "heat"], "current_temperature": 18.0},
    )
    hass.states.async_set(AC_ENTITY, "off")
    hass.states.async_set(CALIBRATION_NUMBER, "0")
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    set_value = async_mock_service(hass, "number", "set_value")
    cid = config_entry.entry_id
    await hass.services.async_call(
        "select",
        "select_option",
        {
            ATTR_ENTITY_ID: entity_id_for("select", f"{cid}_calibration_mode"),
            "option": "offset",
        },
        blocking=True,
    )
    hass.states.async_set(
        entity_id_for("climate", cid),
        "heat_cool",
        {"temperature": 22.5, "preset_mode": "home"},
    )
    hass.states.async_set(AREA_TEMP_SENSOR, "17.0")
    coordinator: SmartClimateCoordinator = config_entry.runtime_data
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    written = [
        c.data["value"]
        for c in set_value
        if c.data[ATTR_ENTITY_ID] == CALIBRATION_NUMBER
    ]
    assert written  # the calibration number was written while heating
    # area 17.0 - TRV's own 18.0 = -1.0
    assert written[-1] == pytest.approx(-1.0, abs=0.01)


async def test_persisted_state_restored_on_load(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """A fresh coordinator restores MPC + maintenance/rmot/bias/demand state."""
    config_entry.add_to_hass(hass)
    saver = SmartClimateCoordinator(hass, config_entry)
    saver._mpc[TRV_ENTITY] = MpcController()
    saver._last_maintenance = 12345.0
    saver._rmot = 18.5
    saver._ac_bias_integral = {AC_ENTITY: 1.25}
    saver._last_demand = {TRV_ENTITY: Demand.HEAT}
    await saver._mpc_store.async_save(saver._mpc_persist_data())
    await saver._maint_store.async_save(saver._state_persist_data())

    fresh = SmartClimateCoordinator(hass, config_entry)
    await fresh.async_load_mpc()

    assert TRV_ENTITY in fresh._mpc
    assert fresh._last_maintenance == 12345.0
    assert fresh._rmot == 18.5
    assert fresh._ac_bias_integral[AC_ENTITY] == 1.25
    assert fresh._last_demand[TRV_ENTITY] is Demand.HEAT


async def test_mpc_fallback_without_valve_number(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """MPC mode without a discoverable valve number degrades gracefully."""
    cid = init_integration.entry_id
    await hass.services.async_call(
        "select",
        "select_option",
        {
            ATTR_ENTITY_ID: entity_id_for("select", f"{cid}_calibration_mode"),
            "option": "mpc",
        },
        blocking=True,
    )
    set_value = async_mock_service(hass, "number", "set_value")
    hass.states.async_set(
        entity_id_for("climate", cid),
        "heat_cool",
        {"temperature": 22.5, "preset_mode": "home"},
    )
    hass.states.async_set(AREA_TEMP_SENSOR, "17.0")
    coordinator: SmartClimateCoordinator = init_integration.runtime_data
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    # No valve number on the TRV's (absent) device -> no valve writes, no crash.
    assert not [c for c in set_value if "valve" in c.data[ATTR_ENTITY_ID]]
    assert hass.states.get(entity_id_for("climate", cid)).state != "unavailable"
