"""Tests for the home-average sensors."""

from __future__ import annotations

from collections.abc import Callable
import math

from homeassistant.const import ATTR_ENTITY_ID, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.climate_orchestrator.control.mpc.controller import MpcController
from custom_components.climate_orchestrator.control.mpc.model import MIN_SAMPLES, Sample
from custom_components.climate_orchestrator.coordinator import SmartClimateCoordinator
from tests.conftest import AREA_TEMP_SENSOR, TRV_ENTITY


async def test_home_average_sensors_report_aggregates(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """The home-wide average sensors expose the aggregates (no entity category)."""
    cid = init_integration.entry_id
    temp_id = entity_id_for("sensor", f"{cid}_home_avg_temperature")
    temp = hass.states.get(temp_id)
    humidity = hass.states.get(entity_id_for("sensor", f"{cid}_home_avg_humidity"))
    assert temp is not None
    assert humidity is not None
    assert float(temp.state) == 21.0
    assert float(humidity.state) == 45.0
    # Primary measurement -> shown under "Sensors", not "Diagnostic".
    assert er.async_get(hass).async_get(temp_id).entity_category is None


async def test_feels_like_sensor_reports_apparent_temperature(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """The feels-like sensor exposes the home apparent temperature (21°C/45%)."""
    cid = init_integration.entry_id
    feels = hass.states.get(
        entity_id_for("sensor", f"{cid}_home_feels_like_temperature")
    )
    assert feels is not None
    # Drier-than-50% air reads a touch below dry-bulb (21.0).
    assert float(feels.state) == pytest.approx(20.7, abs=0.4)


async def test_adaptive_comfort_shifts_band_when_enabled(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """A hot running-mean outdoor temp relaxes only the cool edge when on."""
    cid = init_integration.entry_id
    coordinator: SmartClimateCoordinator = init_integration.runtime_data
    coordinator._rmot = 30.0  # well above the onset (cool edge 24.5 + bias 1)

    await hass.services.async_call(
        "switch",
        "turn_on",
        {ATTR_ENTITY_ID: entity_id_for("switch", f"{cid}_adaptive_cooling_comfort")},
        blocking=True,
    )
    await hass.services.async_call(
        "climate",
        "set_hvac_mode",
        {ATTR_ENTITY_ID: entity_id_for("climate", cid), "hvac_mode": "heat_cool"},
        blocking=True,
    )
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    # Defaults: cool edge 24.5, bias +1 -> onset 25.5; outdoor 30 -> excess 4.5,
    # max_shift 2, response 5. Only the cool edge eases up (there is no
    # adaptive heat-setpoint sensor — the heat edge never moves).
    expected_cool = 24.5 + 2.0 * (1.0 - math.exp(-4.5 / 5.0))
    high = hass.states.get(entity_id_for("sensor", f"{cid}_adaptive_cool_setpoint"))
    assert float(high.state) == pytest.approx(expected_cool, abs=0.05)

    # Mild weather: outdoor 17 is well below the onset, so nothing shifts at all.
    coordinator._rmot = 17.0
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    high = hass.states.get(entity_id_for("sensor", f"{cid}_adaptive_cool_setpoint"))
    assert float(high.state) == pytest.approx(24.5, abs=0.05)


async def test_hvac_action_reason_sensor(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """The reason sensor reads 'off' by default, then explains a heat call."""
    cid = init_integration.entry_id
    reason_id = entity_id_for("sensor", f"{cid}_hvac_action_reason")
    assert hass.states.get(reason_id).state == "off"  # mode defaults to off

    # Turn on into a cold home -> the reason becomes "heating".
    await hass.services.async_call(
        "climate",
        "set_hvac_mode",
        {ATTR_ENTITY_ID: entity_id_for("climate", cid), "hvac_mode": "heat_cool"},
        blocking=True,
    )
    hass.states.async_set(AREA_TEMP_SENSOR, "17.0")
    coordinator: SmartClimateCoordinator = init_integration.runtime_data
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    state = hass.states.get(reason_id)
    assert state.state == "heating"
    assert TRV_ENTITY in state.attributes  # per-device reasons exposed


async def test_temperature_slope_sensor_exists(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """The temperature-slope sensor is created as a home-wide measurement."""
    cid = init_integration.entry_id
    slope_id = entity_id_for("sensor", f"{cid}_temperature_slope")
    assert hass.states.get(slope_id) is not None
    assert er.async_get(hass).async_get(slope_id).entity_category is None


async def test_mpc_diagnostic_sensors_default_when_not_learning(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """Per-TRV MPC sensors exist, are diagnostics, and idle without a model."""
    cid = init_integration.entry_id
    status_id = entity_id_for("sensor", f"{cid}_{TRV_ENTITY}_mpc_learning_status")
    gain_id = entity_id_for("sensor", f"{cid}_{TRV_ENTITY}_mpc_heating_gain")

    assert hass.states.get(status_id).state == "idle"
    registry = er.async_get(hass)
    assert registry.async_get(status_id).entity_category is EntityCategory.DIAGNOSTIC
    assert registry.async_get(gain_id).entity_category is EntityCategory.DIAGNOSTIC


async def test_mpc_learning_status_ready_with_enough_history(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """A controller with enough samples reports the 'ready' learning status."""
    cid = init_integration.entry_id
    coordinator: SmartClimateCoordinator = init_integration.runtime_data
    controller = MpcController()
    for _ in range(MIN_SAMPLES):
        controller.history.append(
            Sample(dt=1.0, temp=20.0, next_temp=20.1, valve=0.5, outdoor=5.0)
        )
    coordinator._runtime(TRV_ENTITY).mpc = controller

    await coordinator.async_refresh()
    await hass.async_block_till_done()

    status_id = entity_id_for("sensor", f"{cid}_{TRV_ENTITY}_mpc_learning_status")
    assert hass.states.get(status_id).state == "ready"
