"""Tests for per-device diagnostics, counters, and operational binary sensors."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
import time

from homeassistant.const import ATTR_ENTITY_ID, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.climate_orchestrator.coordinator import SmartClimateCoordinator
from custom_components.climate_orchestrator.models import RuntimeSample
from tests.conftest import (
    AC_ENTITY,
    AREA_HUMIDITY_SENSOR,
    AREA_TEMP_SENSOR,
    TRV_ENTITY,
)


async def test_per_device_sensors_registered(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """Each device gets action/runtime/cycles diagnostics; valve % is TRV-only."""
    cid = init_integration.entry_id
    registry = er.async_get(hass)

    for key in ("device_action", "device_runtime", "device_cycles_per_hour"):
        for device in (TRV_ENTITY, AC_ENTITY):
            eid = entity_id_for("sensor", f"{cid}_{device}_{key}")
            assert registry.async_get(eid).entity_category is EntityCategory.DIAGNOSTIC

    # Valve position exists for the TRV only.
    assert (
        registry.async_get_entity_id(
            "sensor", "climate_orchestrator", f"{cid}_{TRV_ENTITY}_valve_position"
        )
        is not None
    )
    assert (
        registry.async_get_entity_id(
            "sensor", "climate_orchestrator", f"{cid}_{AC_ENTITY}_valve_position"
        )
        is None
    )
    # MPC diagnostics are folded into one learning-status sensor for the TRV;
    # the retired per-value sensors are never created.
    assert (
        registry.async_get_entity_id(
            "sensor", "climate_orchestrator", f"{cid}_{TRV_ENTITY}_mpc_learning_status"
        )
        is not None
    )
    for retired in ("mpc_heating_gain", "mpc_heat_loss", "mpc_model_error"):
        assert (
            registry.async_get_entity_id(
                "sensor", "climate_orchestrator", f"{cid}_{TRV_ENTITY}_{retired}"
            )
            is None
        )


async def test_device_action_and_frost_binary_sensor(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """A freezing room drives the TRV to heat and lights the frost binary sensor."""
    cid = init_integration.entry_id
    coordinator: SmartClimateCoordinator = init_integration.runtime_data

    await hass.services.async_call(
        "climate",
        "set_hvac_mode",
        {ATTR_ENTITY_ID: entity_id_for("climate", cid), "hvac_mode": "heat_cool"},
        blocking=True,
    )
    hass.states.async_set(AREA_TEMP_SENSOR, "5.0", {"device_class": "temperature"})
    # Advertise heat capability so the built command is actually HEAT (not off).
    hass.states.async_set(TRV_ENTITY, "heat", {"hvac_modes": ["off", "heat"]})
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    action_id = entity_id_for("sensor", f"{cid}_{TRV_ENTITY}_device_action")
    action = hass.states.get(action_id)
    assert action.state == "heating"
    assert action.attributes["commanded_mode"] == "heat"

    frost = hass.states.get(entity_id_for("binary_sensor", f"{cid}_frost_active"))
    window = hass.states.get(entity_id_for("binary_sensor", f"{cid}_window_open"))
    assert frost.state == "on"
    assert window.state == "off"


async def test_runtime_and_cycle_counters(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
) -> None:
    """The rolling counters integrate run-time and count off->on starts."""
    coordinator: SmartClimateCoordinator = init_integration.runtime_data
    now = time.monotonic()
    # Over the last hour: off, on@-1800s, off@-900s, on@-600s.
    coordinator._runtime(TRV_ENTITY).run_samples = deque(
        [
            RuntimeSample(at=now - 3600.0, running=False),
            RuntimeSample(at=now - 1800.0, running=True),
            RuntimeSample(at=now - 900.0, running=False),
            RuntimeSample(at=now - 600.0, running=True),
        ]
    )
    # ~900s + ~600s running out of ~3600s.
    assert coordinator.device_runtime_fraction(TRV_ENTITY) == pytest.approx(
        0.417, abs=0.03
    )
    # Two off->on transitions in the window.
    assert coordinator.device_cycles_per_hour(TRV_ENTITY) == pytest.approx(2.0, abs=0.1)


async def test_dehumidify_action_and_dew_point_binary_sensor(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """High humidity (not hot enough to cool) puts the AC in dry mode."""
    cid = init_integration.entry_id
    coordinator: SmartClimateCoordinator = init_integration.runtime_data

    # Comfort off so the muggy air isn't read as hot enough to actively cool.
    await hass.services.async_call(
        "switch",
        "turn_off",
        {ATTR_ENTITY_ID: entity_id_for("switch", f"{cid}_comfort_index_targeting")},
        blocking=True,
    )
    await hass.services.async_call(
        "climate",
        "set_hvac_mode",
        {ATTR_ENTITY_ID: entity_id_for("climate", cid), "hvac_mode": "heat_cool"},
        blocking=True,
    )
    # 24 C is below the cool edge (24.5) but 90% RH -> dew point ~22 C > 16 C.
    hass.states.async_set(AREA_TEMP_SENSOR, "24.0", {"device_class": "temperature"})
    hass.states.async_set(AREA_HUMIDITY_SENSOR, "90", {"device_class": "humidity"})
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    ac_action = hass.states.get(
        entity_id_for("sensor", f"{cid}_{AC_ENTITY}_device_action")
    )
    dew = hass.states.get(entity_id_for("binary_sensor", f"{cid}_dew_point_active"))
    reason = hass.states.get(entity_id_for("sensor", f"{cid}_hvac_action_reason"))
    assert ac_action.state == "drying"
    assert dew.state == "on"
    assert reason.state == "dehumidifying"


async def test_operational_binary_sensors_exist(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """The three operational binary sensors are created and non-diagnostic."""
    cid = init_integration.entry_id
    registry = er.async_get(hass)
    for key in ("window_open", "frost_active", "dew_point_active"):
        eid = entity_id_for("binary_sensor", f"{cid}_{key}")
        assert registry.async_get(eid).entity_category is None
