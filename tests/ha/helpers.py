"""Shared helpers for the hass-fixture tests (plain functions, not fixtures)."""

from __future__ import annotations

import time
from typing import Any

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    ATTR_PRESET_MODE,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_PRESET_MODE,
    HVACMode,
)
from homeassistant.components.climate import (
    DOMAIN as CLIMATE_DOMAIN,
)
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.climate_orchestrator.const import (
    DEFAULT_PRESET,
    DOMAIN,
    FORECAST_FAILURE_SECONDS,
    STARTUP_GRACE_SECONDS,
)
from custom_components.climate_orchestrator.coordinator import (
    DeviceRuntime,
    SmartClimateCoordinator,
)
from tests.conftest import AC_ENTITY, TRV_ENTITY

# Canonical capability attributes for the fake devices (shared across suites).
TRV_ATTRS = {
    "hvac_modes": ["off", "heat"],
    "min_temp": 7.0,
    "max_temp": 35.0,
    "target_temp_step": 0.5,
}
AC_ATTRS = {
    "hvac_modes": ["off", "cool", "dry"],
    "min_temp": 16.0,
    "max_temp": 30.0,
    "target_temp_step": 0.5,
}


async def set_desired_preset(
    hass: HomeAssistant,
    climate_id: str,
    mode: str | None = None,
    *,
    preset: str = DEFAULT_PRESET,
) -> None:
    """Put the whole-home entity into ``mode`` on ``preset``, via its services.

    Driving the real services is what makes this stick. Writing the state
    directly (``hass.states.async_set``) does not: the climate entity writes
    its own state during the control cycle, so from HA 2026.8 the faked state
    is overwritten *before* the coordinator reads it and every device falls
    through to the ``master_off`` decision.

    ``mode`` defaults to whichever "on" mode the configured hardware exposes
    (``heat_cool`` for a TRV+AC home, ``heat``/``cool`` for a single-purpose
    one) — unlike a faked state, a real service call rejects a mode the entity
    doesn't support.
    """
    if mode is None:
        state = hass.states.get(climate_id)
        assert state is not None, f"{climate_id} has no state"
        mode = next(m for m in state.attributes["hvac_modes"] if m != HVACMode.OFF)
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_HVAC_MODE,
        {ATTR_ENTITY_ID: climate_id, ATTR_HVAC_MODE: mode},
        blocking=True,
    )
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_PRESET_MODE,
        {ATTR_ENTITY_ID: climate_id, ATTR_PRESET_MODE: preset},
        blocking=True,
    )


async def select_calibration_mode(
    hass: HomeAssistant, entry_id: str, mode: str
) -> None:
    """Pick a TRV calibration mode via the select entity, as the UI would.

    Requires the integration set up for ``entry_id`` (the select platform
    must have created the calibration-mode entity).
    """
    entity_id = er.async_get(hass).async_get_entity_id(
        "select", DOMAIN, f"{entry_id}_calibration_mode"
    )
    assert entity_id is not None
    await hass.services.async_call(
        "select",
        "select_option",
        {ATTR_ENTITY_ID: entity_id, "option": mode},
        blocking=True,
    )


async def setup_trv_with_number(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    area_id: str,
    *,
    number_suffix: str = "valve_opening_degree",
    number_value: str = "0",
    trv_attrs: dict[str, Any] | None = None,
) -> SmartClimateCoordinator:
    """Set up the integration with a TRV exposing a related ``number`` entity.

    Registers the TRV in ``area_id`` together with a number entity on the
    same device, named so the valve/calibration hints can discover it — the
    full device/entity-registry wiring the mpc/offset test paths need.

    Call INSTEAD of the ``init_integration`` fixture (it sets up the config
    entry itself); ``number_suffix`` must match one of the discovery hints
    (``valve_opening_degree`` for mpc, ``local_temperature_calibration``
    for offset) or the calibration paths fall back to ``target``.
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
    registry.async_update_entity(climate.entity_id, area_id=area_id)
    registry.async_get_or_create(
        "number",
        "test",
        f"u_{number_suffix}",
        suggested_object_id=f"trv_1_{number_suffix}",
        device_id=device.id,
    )
    hass.states.async_set(
        TRV_ENTITY, "heat", {"hvac_modes": ["off", "heat"], **(trv_attrs or {})}
    )
    hass.states.async_set(AC_ENTITY, "off")
    hass.states.async_set(f"number.trv_1_{number_suffix}", number_value)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry.runtime_data


async def refresh(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Run one control cycle and settle the event loop."""
    coordinator: SmartClimateCoordinator = entry.runtime_data
    await coordinator.async_refresh()
    await hass.async_block_till_done()


# --- Coordinator internals: the single point of private access -------------
#
# Tests legitimately manipulate coordinator-internal state (simulated clocks,
# injected learned models, store round-trips). ALL such access lives behind
# the helpers below — production refactors may break this section, but never
# the test files themselves. Do not touch `coordinator._*` anywhere else.


def runtime(coordinator: SmartClimateCoordinator, entity_id: str) -> DeviceRuntime:
    """The device's mutable runtime state (read or seed fields directly)."""
    return coordinator._runtime(entity_id)


def has_runtime(coordinator: SmartClimateCoordinator, entity_id: str) -> bool:
    """Whether a runtime exists for the device (eviction checks)."""
    return entity_id in coordinator._devices


def mpc_payload(coordinator: SmartClimateCoordinator) -> dict[str, Any]:
    """The MPC store payload the coordinator would persist right now."""
    return coordinator._mpc_persist_data()


def state_payload(coordinator: SmartClimateCoordinator) -> dict[str, Any]:
    """The slow-state store payload (rmot, bias, demand, maintenance clock)."""
    return coordinator._state_persist_data()


def mpc_store(coordinator: SmartClimateCoordinator) -> Any:
    """The learned-MPC Store (simulate restores by saving crafted payloads)."""
    return coordinator._stores._mpc_store


def state_store(coordinator: SmartClimateCoordinator) -> Any:
    """The slow-state Store (maintenance clock, rmot, bias integrals)."""
    return coordinator._stores._state_store


def expire_persist_limiter(coordinator: SmartClimateCoordinator) -> None:
    """Make the flash-wear rate limiter consider a persist due now."""
    coordinator._stores._last_persist = time.monotonic() - 1000.0


def maintenance_clock(coordinator: SmartClimateCoordinator) -> float | None:
    """Wall-clock epoch of the last valve maintenance run (None = never)."""
    return coordinator.last_maintenance


def set_maintenance_clock(
    coordinator: SmartClimateCoordinator, when: float | None
) -> None:
    """Set the last-maintenance epoch (e.g. far in the past = overdue)."""
    coordinator._last_maintenance = when


def set_maintenance_running(
    coordinator: SmartClimateCoordinator, *, value: bool
) -> None:
    """Mark a valve-maintenance run as in flight (re-entrancy tests)."""
    coordinator._maintenance_running = value


def evaluate_mpc_fit(
    coordinator: SmartClimateCoordinator, entity_id: str, controller: Any
) -> None:
    """Run the poor-fit repair evaluation for a device's MPC controller."""
    coordinator._evaluate_mpc_fit(entity_id, controller)


def rmot(coordinator: SmartClimateCoordinator) -> float | None:
    """The running-mean outdoor temperature driving adaptive comfort."""
    return coordinator.running_mean_outdoor


def set_rmot(coordinator: SmartClimateCoordinator, value: float) -> None:
    """Seed the running-mean outdoor temperature (skip the slow EMA warm-up)."""
    coordinator._adaptation.rmot = value


def window_timers(coordinator: SmartClimateCoordinator) -> dict[str, float]:
    """Per-area window-open-since timers (mutate to inject/inspect)."""
    return coordinator._windows._open_since


def cancel_window_recheck(coordinator: SmartClimateCoordinator) -> None:
    """Drop any pending window grace-delay recheck timer."""
    coordinator._windows.shutdown()


def window_recheck_deadline(coordinator: SmartClimateCoordinator) -> float | None:
    """Monotonic deadline of the pending window recheck (None = none armed)."""
    monitor = coordinator._windows
    if monitor._recheck_unsub is None:
        return None
    return monitor._recheck_at


def forecast_cache(coordinator: SmartClimateCoordinator) -> list[float]:
    """The cached hourly forecast temperatures."""
    return coordinator._adaptation._forecast_hourly


def expire_forecast(coordinator: SmartClimateCoordinator) -> None:
    """Age the cached forecast past the staleness cap (dead weather entity)."""
    coordinator._adaptation._forecast_fetched_at = time.monotonic() - 4.0 * 3600.0


def age_forecast_failure(coordinator: SmartClimateCoordinator) -> None:
    """Push the forecast-fetch-failure clock past the repair threshold."""
    coordinator._adaptation._fetch_failing_since = (
        time.monotonic() - FORECAST_FAILURE_SECONDS - 10.0
    )


def precondition_series(
    coordinator: SmartClimateCoordinator, dt_minutes: float, settings: Any
) -> list[float] | None:
    """The forecast series the MPC preconditioner would optimise against."""
    return coordinator._adaptation.precondition_series(dt_minutes, settings)


def expire_startup_grace(coordinator: SmartClimateCoordinator) -> None:
    """Pretend the post-restart warm-up window has fully elapsed."""
    coordinator._started -= STARTUP_GRACE_SECONDS + 10.0


def spawn_background(
    coordinator: SmartClimateCoordinator, coro: Any, name: str
) -> None:
    """Schedule a coroutine the way the coordinator does (entry-tracked)."""
    coordinator._background(coro, name)
