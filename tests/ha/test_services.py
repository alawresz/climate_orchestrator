"""Tests for the maintenance/reset services and auto valve maintenance."""

from __future__ import annotations

from collections.abc import Callable
import time
from unittest.mock import AsyncMock, patch

from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.climate_orchestrator.const import DOMAIN
from custom_components.climate_orchestrator.control.mpc.controller import MpcController
from tests.conftest import AREA_TEMP_SENSOR, TRV_ENTITY
from tests.ha.helpers import (
    maintenance_clock,
    runtime,
    set_desired_preset,
    set_maintenance_clock,
    set_maintenance_running,
    setup_trv_with_number,
)

VALVE_NUMBER = "number.trv_1_valve_opening_degree"
_NO_SLEEP = "custom_components.climate_orchestrator.coordinator.asyncio.sleep"


async def test_valve_maintenance_cycles_the_valve(
    hass: HomeAssistant, config_entry: MockConfigEntry, living_area: str
) -> None:
    """Maintenance drives the valve fully open then fully closed."""
    coordinator = await setup_trv_with_number(
        hass, config_entry, living_area, number_value="50"
    )
    set_value = async_mock_service(hass, "number", "set_value")

    await coordinator.async_run_valve_maintenance(dwell=0)
    await hass.async_block_till_done()

    written = [
        c.data["value"] for c in set_value if c.data[ATTR_ENTITY_ID] == VALVE_NUMBER
    ]
    assert 100.0 in written
    assert 0.0 in written


async def test_run_valve_maintenance_service(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    living_area: str,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """The service is registered on the whole-home entity and exercises valves."""
    await setup_trv_with_number(hass, config_entry, living_area, number_value="50")
    set_value = async_mock_service(hass, "number", "set_value")
    climate_id = entity_id_for("climate", config_entry.entry_id)

    with patch(_NO_SLEEP, new=AsyncMock()):
        await hass.services.async_call(
            DOMAIN,
            "run_valve_maintenance",
            {ATTR_ENTITY_ID: climate_id},
            blocking=True,
        )
        await hass.async_block_till_done()

    assert any(c.data[ATTR_ENTITY_ID] == VALVE_NUMBER for c in set_value)


async def test_reset_mpc_learning_service(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    living_area: str,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """The reset service forgets the learned MPC controllers."""
    coordinator = await setup_trv_with_number(
        hass, config_entry, living_area, number_value="50"
    )
    runtime(coordinator, TRV_ENTITY).mpc = MpcController()

    await hass.services.async_call(
        DOMAIN,
        "reset_mpc_learning",
        {ATTR_ENTITY_ID: entity_id_for("climate", config_entry.entry_id)},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert runtime(coordinator, TRV_ENTITY).mpc is None


async def test_auto_valve_maintenance_runs_when_due(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    living_area: str,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """With the flag on and the interval elapsed, a control cycle runs it."""
    coordinator = await setup_trv_with_number(
        hass, config_entry, living_area, number_value="50"
    )
    set_value = async_mock_service(hass, "number", "set_value")
    cid = config_entry.entry_id

    await hass.services.async_call(
        "switch",
        "turn_on",
        {ATTR_ENTITY_ID: entity_id_for("switch", f"{cid}_auto_valve_maintenance")},
        blocking=True,
    )
    set_maintenance_clock(coordinator, time.time() - 30 * 86400)  # long overdue

    with patch(_NO_SLEEP, new=AsyncMock()):
        await coordinator.async_refresh()
        # Auto maintenance runs as an entry-tracked *background* task, which
        # plain block_till_done deliberately doesn't wait for.
        await hass.async_block_till_done(wait_background_tasks=True)

    assert any(c.data[ATTR_ENTITY_ID] == VALVE_NUMBER for c in set_value)


async def test_auto_maintenance_without_valves_warns_and_restarts_clock(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """No valve numbers: auto maintenance warns once and waits a full interval.

    Without the clock restart the run would stay "due" and respawn a silent
    no-op background task on every cycle.
    """
    coordinator = init_integration.runtime_data
    cid = init_integration.entry_id
    await hass.services.async_call(
        "switch",
        "turn_on",
        {ATTR_ENTITY_ID: entity_id_for("switch", f"{cid}_auto_valve_maintenance")},
        blocking=True,
    )
    set_maintenance_clock(coordinator, time.time() - 365 * 86400)  # long overdue

    await coordinator.async_refresh()
    await hass.async_block_till_done(wait_background_tasks=True)

    assert "found no valve" in caplog.text
    # The clock restarted: no longer due, so the next cycle stays quiet.
    assert maintenance_clock(coordinator) >= time.time() - 60
    caplog.clear()
    await coordinator.async_refresh()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert "found no valve" not in caplog.text


async def test_auto_maintenance_defers_while_a_trv_heats(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    living_area: str,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """Due maintenance waits rather than interrupting active heating.

    Cycling the valve to 100 then 0 mid-heat would visibly disturb the room;
    the run simply stays due until a cycle where no TRV demands heat.
    """
    coordinator = await setup_trv_with_number(
        hass, config_entry, living_area, number_value="50"
    )
    set_value = async_mock_service(hass, "number", "set_value")
    cid = config_entry.entry_id
    await hass.services.async_call(
        "switch",
        "turn_on",
        {ATTR_ENTITY_ID: entity_id_for("switch", f"{cid}_auto_valve_maintenance")},
        blocking=True,
    )
    # Get the room cold and the system on first, so the TRV is already heating.
    # Any cycle that runs while it isn't — and switching the entity on, or even
    # writing the sensor state, runs one — would find nothing to defer to and
    # let the overdue maintenance through, which is exactly what this asserts
    # doesn't happen. Making the clock overdue last removes that window.
    hass.states.async_set(AREA_TEMP_SENSOR, "17.0")
    await set_desired_preset(hass, entity_id_for("climate", cid))
    overdue = time.time() - 30 * 86400
    set_maintenance_clock(coordinator, overdue)

    await coordinator.async_refresh()
    await hass.async_block_till_done(wait_background_tasks=True)

    assert coordinator.device_action(TRV_ENTITY) == "heating"
    # No maintenance ran: the clock still reads overdue, no valve cycling.
    assert maintenance_clock(coordinator) == overdue
    written = [
        c.data["value"] for c in set_value if c.data[ATTR_ENTITY_ID] == VALVE_NUMBER
    ]
    assert 100.0 not in written


async def test_overlapping_maintenance_triggers_do_not_stack(
    hass: HomeAssistant, config_entry: MockConfigEntry, living_area: str
) -> None:
    """A maintenance trigger while one is already running is a quiet no-op."""
    coordinator = await setup_trv_with_number(
        hass, config_entry, living_area, number_value="50"
    )
    set_value = async_mock_service(hass, "number", "set_value")

    set_maintenance_running(coordinator, value=True)
    try:
        assert await coordinator.async_run_valve_maintenance(dwell=0) is True
    finally:
        set_maintenance_running(coordinator, value=False)

    # The overlapping trigger reported success but cycled nothing.
    assert not [c for c in set_value if c.data[ATTR_ENTITY_ID] == VALVE_NUMBER]


async def test_valve_maintenance_without_valves_raises_translated_error(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """No discoverable valve numbers -> ServiceValidationError, not a no-op."""
    climate_id = entity_id_for("climate", init_integration.entry_id)
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN,
            "run_valve_maintenance",
            {ATTR_ENTITY_ID: climate_id},
            blocking=True,
        )
    assert err.value.translation_key == "no_maintenance_valves"


async def test_future_maintenance_timestamp_is_reset_not_trusted(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    living_area: str,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """Wall-clock skew (NTP jump, restored backup) can't defer maintenance.

    A last-maintenance timestamp in the future is reset to now instead of
    silently postponing the next run by up to a full interval past the lie.
    """
    coordinator = await setup_trv_with_number(
        hass, config_entry, living_area, number_value="50"
    )
    set_value = async_mock_service(hass, "number", "set_value")
    cid = config_entry.entry_id
    await hass.services.async_call(
        "switch",
        "turn_on",
        {ATTR_ENTITY_ID: entity_id_for("switch", f"{cid}_auto_valve_maintenance")},
        blocking=True,
    )
    set_maintenance_clock(coordinator, time.time() + 365 * 86400)  # a year ahead

    await coordinator.async_refresh()
    await hass.async_block_till_done(wait_background_tasks=True)

    # The clock restarted from now: no maintenance ran, timestamp is sane.
    assert not [c for c in set_value if c.data[ATTR_ENTITY_ID] == VALVE_NUMBER]
    assert maintenance_clock(coordinator) is not None
    assert maintenance_clock(coordinator) <= time.time()
