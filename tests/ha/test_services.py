"""Tests for the maintenance/reset services and auto valve maintenance."""

from __future__ import annotations

from collections.abc import Callable
import time
from unittest.mock import AsyncMock, patch

from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.climate_orchestrator.const import DOMAIN
from custom_components.climate_orchestrator.control.mpc.controller import MpcController
from custom_components.climate_orchestrator.coordinator import SmartClimateCoordinator
from tests.conftest import AC_ENTITY, TRV_ENTITY

VALVE_NUMBER = "number.trv_1_valve_opening_degree"
_NO_SLEEP = "custom_components.climate_orchestrator.coordinator.asyncio.sleep"


async def _setup_with_valve(
    hass: HomeAssistant, config_entry: MockConfigEntry, area_id: str
) -> SmartClimateCoordinator:
    """Set up the integration with a TRV that exposes a valve-opening number."""
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
    hass.states.async_set(TRV_ENTITY, "heat", {"hvac_modes": ["off", "heat"]})
    hass.states.async_set(AC_ENTITY, "off")
    hass.states.async_set(VALVE_NUMBER, "50")
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry.runtime_data


async def test_valve_maintenance_cycles_the_valve(
    hass: HomeAssistant, config_entry: MockConfigEntry, living_area: str
) -> None:
    """Maintenance drives the valve fully open then fully closed."""
    coordinator = await _setup_with_valve(hass, config_entry, living_area)
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
    await _setup_with_valve(hass, config_entry, living_area)
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
    coordinator = await _setup_with_valve(hass, config_entry, living_area)
    coordinator._runtime(TRV_ENTITY).mpc = MpcController()

    await hass.services.async_call(
        DOMAIN,
        "reset_mpc_learning",
        {ATTR_ENTITY_ID: entity_id_for("climate", config_entry.entry_id)},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert coordinator._runtime(TRV_ENTITY).mpc is None


async def test_auto_valve_maintenance_runs_when_due(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    living_area: str,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """With the flag on and the interval elapsed, a control cycle runs it."""
    coordinator = await _setup_with_valve(hass, config_entry, living_area)
    set_value = async_mock_service(hass, "number", "set_value")
    cid = config_entry.entry_id

    await hass.services.async_call(
        "switch",
        "turn_on",
        {ATTR_ENTITY_ID: entity_id_for("switch", f"{cid}_auto_valve_maintenance")},
        blocking=True,
    )
    coordinator._last_maintenance = time.time() - 30 * 86400  # long overdue

    with patch(_NO_SLEEP, new=AsyncMock()):
        await coordinator.async_refresh()
        await hass.async_block_till_done()

    assert any(c.data[ATTR_ENTITY_ID] == VALVE_NUMBER for c in set_value)
