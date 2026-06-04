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
from tests.conftest import TRV_ENTITY
from tests.ha.helpers import setup_trv_with_number

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
    coordinator._last_maintenance = time.time() - 30 * 86400  # long overdue

    with patch(_NO_SLEEP, new=AsyncMock()):
        await coordinator.async_refresh()
        await hass.async_block_till_done()

    assert any(c.data[ATTR_ENTITY_ID] == VALVE_NUMBER for c in set_value)


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
