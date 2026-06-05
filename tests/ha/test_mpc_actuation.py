"""Tests for MPC/offset calibration driving a TRV's valve number."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from unittest.mock import patch

from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.climate_orchestrator.control.hysteresis import Demand
from custom_components.climate_orchestrator.control.mpc.controller import MpcController
from custom_components.climate_orchestrator.coordinator import SmartClimateCoordinator
from tests.conftest import AC_ENTITY, AREA_TEMP_SENSOR, TRV_ENTITY
from tests.ha.helpers import (
    expire_persist_limiter,
    has_runtime,
    maintenance_clock,
    mpc_payload,
    mpc_store,
    rmot,
    runtime,
    select_calibration_mode,
    set_desired_preset,
    set_maintenance_clock,
    set_rmot,
    setup_trv_with_number,
    state_payload,
    state_store,
)

VALVE_NUMBER = "number.trv_1_valve_opening_degree"
CALIBRATION_NUMBER = "number.trv_1_local_temperature_calibration"
# The TRV reports its own (low) internal reading alongside the room sensor.
_TRV_ATTRS = {"current_temperature": 18.0, "temperature": 21.0}


async def _engage_mpc_heating(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
) -> SmartClimateCoordinator:
    """Switch to MPC, then turn the system on into a cold room and recompute."""
    cid = config_entry.entry_id
    await select_calibration_mode(hass, cid, "mpc")
    set_desired_preset(hass, entity_id_for("climate", cid))
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
    await setup_trv_with_number(hass, config_entry, living_area, trv_attrs=_TRV_ATTRS)
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
    await setup_trv_with_number(hass, config_entry, living_area, trv_attrs=_TRV_ATTRS)
    # Pretend the valve was left open from an earlier heating run.
    hass.states.async_set(VALVE_NUMBER, "80")
    set_value = async_mock_service(hass, "number", "set_value")

    cid = config_entry.entry_id
    await select_calibration_mode(hass, cid, "mpc")
    # A warm room -> the heater idles (it can't cool), so the valve must close.
    set_desired_preset(hass, entity_id_for("climate", cid))
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
    """Once a controller exists, the status moves and the model rides as attrs."""
    await setup_trv_with_number(hass, config_entry, living_area, trv_attrs=_TRV_ATTRS)
    async_mock_service(hass, "number", "set_value")
    await _engage_mpc_heating(hass, config_entry, entity_id_for)

    cid = config_entry.entry_id
    status = hass.states.get(
        entity_id_for("sensor", f"{cid}_{TRV_ENTITY}_mpc_learning_status")
    )
    assert status.state in ("learning", "ready")
    assert status.attributes["heating_gain"] >= 0.0
    assert status.attributes["heat_loss"] >= 0.0
    # A fresh controller's first observation only anchors the model; the first
    # (dt, temp -> next_temp) sample pair lands on the *next* cycle.
    assert status.attributes["samples"] >= 0


async def test_mpc_state_is_persisted(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    living_area: str,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """A controller is created and its state is serialisable for persistence."""
    await setup_trv_with_number(hass, config_entry, living_area, trv_attrs=_TRV_ATTRS)
    async_mock_service(hass, "number", "set_value")
    coordinator = await _engage_mpc_heating(hass, config_entry, entity_id_for)

    persisted = mpc_payload(coordinator)
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
    await setup_trv_with_number(
        hass,
        config_entry,
        living_area,
        number_suffix="local_temperature_calibration",
        trv_attrs={"current_temperature": 18.0},
    )

    set_value = async_mock_service(hass, "number", "set_value")
    cid = config_entry.entry_id
    await select_calibration_mode(hass, cid, "offset")
    set_desired_preset(hass, entity_id_for("climate", cid))
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
    runtime(saver, TRV_ENTITY).mpc = MpcController()
    set_maintenance_clock(saver, 12345.0)
    set_rmot(saver, 18.5)
    runtime(saver, AC_ENTITY).ac_bias_integral = 1.25
    runtime(saver, TRV_ENTITY).demand = Demand.HEAT
    await mpc_store(saver).async_save(mpc_payload(saver))
    await state_store(saver).async_save(state_payload(saver))

    fresh = SmartClimateCoordinator(hass, config_entry)
    await fresh.async_load_mpc()

    assert runtime(fresh, TRV_ENTITY).mpc is not None
    assert maintenance_clock(fresh) == 12345.0
    assert rmot(fresh) == 18.5
    assert runtime(fresh, AC_ENTITY).ac_bias_integral == 1.25
    assert runtime(fresh, TRV_ENTITY).demand is Demand.HEAT


async def test_mpc_fallback_without_valve_number(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """MPC mode without a discoverable valve number degrades gracefully."""
    cid = init_integration.entry_id
    await select_calibration_mode(hass, cid, "mpc")
    set_value = async_mock_service(hass, "number", "set_value")
    set_desired_preset(hass, entity_id_for("climate", cid))
    hass.states.async_set(AREA_TEMP_SENSOR, "17.0")
    coordinator: SmartClimateCoordinator = init_integration.runtime_data
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    # No valve number on the TRV's (absent) device -> no valve writes, no crash.
    assert not [c for c in set_value if "valve" in c.data[ATTR_ENTITY_ID]]
    assert hass.states.get(entity_id_for("climate", cid)).state != "unavailable"


async def test_corrupt_persisted_mpc_state_does_not_break_load(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """A corrupt store entry is discarded (fresh learning), not a setup crash."""
    config_entry.add_to_hass(hass)
    saver = SmartClimateCoordinator(hass, config_entry)
    await mpc_store(saver).async_save(
        {TRV_ENTITY: {"gain": "garbage"}, AC_ENTITY: MpcController().to_dict()}
    )

    fresh = SmartClimateCoordinator(hass, config_entry)
    await fresh.async_load_mpc()

    assert runtime(fresh, TRV_ENTITY).mpc is None  # corrupt entry discarded
    assert runtime(fresh, AC_ENTITY).mpc is not None  # valid entry restored


async def test_persisted_state_for_unmanaged_devices_is_dropped(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """Store keys for devices no longer in the config don't resurrect.

    The persist methods dump the runtime dict wholesale, so a stale key
    restored once would otherwise cycle store -> runtime -> store forever.
    """
    config_entry.add_to_hass(hass)
    saver = SmartClimateCoordinator(hass, config_entry)
    await mpc_store(saver).async_save(
        {
            TRV_ENTITY: MpcController().to_dict(),
            "climate.removed_trv": MpcController().to_dict(),
        }
    )
    await state_store(saver).async_save(
        {
            "last": 12345.0,
            "rmot": 18.5,
            "ac_bias_integral": {AC_ENTITY: 1.0, "climate.removed_ac": 2.0},
            "last_demand": {TRV_ENTITY: "heat", "climate.removed_trv": "heat"},
        }
    )

    fresh = SmartClimateCoordinator(hass, config_entry)
    await fresh.async_load_mpc()
    assert runtime(fresh, TRV_ENTITY).mpc is not None
    assert not has_runtime(fresh, "climate.removed_trv")
    assert not has_runtime(fresh, "climate.removed_ac")
    # The next persist no longer carries the stale keys.
    assert "climate.removed_trv" not in mpc_payload(fresh)
    assert "climate.removed_ac" not in state_payload(fresh)["ac_bias_integral"]


async def test_learned_state_saves_are_rate_limited(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Slow-moving learned state is persisted at most every _PERSIST_INTERVAL.

    Saving "on change" would mean one flash write per cycle forever (rmot is
    a continuously-updated EMA) — SD-card wear on typical HA boxes.
    """
    coordinator: SmartClimateCoordinator = init_integration.runtime_data
    with patch.object(state_store(coordinator), "async_delay_save") as delay_save:
        # Setup's first cycle already scheduled a save: within the interval.
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert delay_save.call_count == 0

        # Interval elapsed but nothing changed -> still no write scheduled.
        expire_persist_limiter(coordinator)
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert delay_save.call_count == 0

        # Interval elapsed and the payload changed -> exactly one schedule.
        set_rmot(coordinator, 12.34)
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert delay_save.call_count == 1


async def test_future_version_store_is_discarded_not_fatal(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_storage: dict[str, Any],
) -> None:
    """A store written by a newer release (downgrade) must not break setup.

    ``Store`` raises ``UnsupportedStorageVersionError`` for a newer major —
    learned state is re-learnable, so it's discarded with a warning instead.
    """
    config_entry.add_to_hass(hass)
    for suffix in ("mpc", "maintenance"):
        key = f"climate_orchestrator.{config_entry.entry_id}.{suffix}"
        hass_storage[key] = {
            "version": 99,
            "minor_version": 1,
            "key": key,
            "data": {"schema": "from the future"},
        }

    fresh = SmartClimateCoordinator(hass, config_entry)
    await fresh.async_load_mpc()  # must not raise
    assert runtime(fresh, TRV_ENTITY).mpc is None
    assert maintenance_clock(fresh) is None


async def test_unknown_older_schema_migrates_to_empty(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_storage: dict[str, Any],
) -> None:
    """An unrecognised *older* major is discarded by the migrate hook."""
    config_entry.add_to_hass(hass)
    key = f"climate_orchestrator.{config_entry.entry_id}.mpc"
    hass_storage[key] = {
        "version": 0,
        "minor_version": 1,
        "key": key,
        "data": {TRV_ENTITY: {"pre_release": True}},
    }

    fresh = SmartClimateCoordinator(hass, config_entry)
    await fresh.async_load_mpc()  # must not raise
    assert runtime(fresh, TRV_ENTITY).mpc is None
