"""Tests for the Repairs (issue registry) integration."""

from __future__ import annotations

from collections.abc import Callable
import time

from homeassistant.const import ATTR_ENTITY_ID, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
)

from custom_components.climate_orchestrator.const import (
    CONF_TRVS,
    CONTROL_FAILURE_ISSUE_THRESHOLD,
    DEFAULT_TITLE,
    DOMAIN,
    MPC_POOR_FIT_SECONDS,
)
from custom_components.climate_orchestrator.control.mpc.controller import MpcController
from custom_components.climate_orchestrator.control.mpc.model import (
    Sample,
    ThermalParams,
)
from custom_components.climate_orchestrator.coordinator import SmartClimateCoordinator
from tests.conftest import AC_ENTITY, AREA_HUMIDITY_SENSOR, AREA_TEMP_SENSOR, TRV_ENTITY
from tests.ha.helpers import evaluate_mpc_fit, refresh, runtime

# An AC advertising both heat and dry modes (reverse-cycle unit); the
# init_integration fixture's AC reports no modes, so it can neither.
_AC_HEAT_DRY = {"hvac_modes": ["off", "cool", "heat", "dry"]}


async def _setup_trv_only(
    hass: HomeAssistant,
    living_area: str,
    register_entity_in_area: Callable[[str, str | None], str],
) -> MockConfigEntry:
    """A radiator-only home (no AC configured) with a usable temperature."""
    register_entity_in_area(TRV_ENTITY, living_area)
    hass.states.async_set(TRV_ENTITY, "heat", {"hvac_modes": ["off", "heat"]})
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_TITLE,
        data={CONF_TRVS: [TRV_ENTITY]},
        entry_id="sc_trv_only_repairs",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _turn_on(
    hass: HomeAssistant, entity_id_for: Callable[[str, str], str], cid: str, key: str
) -> None:
    await hass.services.async_call(
        "switch",
        "turn_on",
        {ATTR_ENTITY_ID: entity_id_for("switch", f"{cid}_{key}")},
        blocking=True,
    )


async def _turn_off(
    hass: HomeAssistant, entity_id_for: Callable[[str, str], str], cid: str, key: str
) -> None:
    await hass.services.async_call(
        "switch",
        "turn_off",
        {ATTR_ENTITY_ID: entity_id_for("switch", f"{cid}_{key}")},
        blocking=True,
    )


async def test_heating_assist_without_heat_capable_ac_raises_and_clears(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """Assist on while the AC has no heat mode raises; gaining one clears it.

    The engine produces a HEAT demand for the AC, but ``build_command`` drops
    it (no ``heat`` capability) — assist silently does nothing.
    """
    registry = ir.async_get(hass)
    cid = init_integration.entry_id
    # Assist is off by default -> no issue even though the AC can't heat.
    assert registry.async_get_issue(DOMAIN, "heating_assist_unavailable") is None

    await _turn_on(hass, entity_id_for, cid, "ac_heating_assist")
    await refresh(hass, init_integration)
    assert registry.async_get_issue(DOMAIN, "heating_assist_unavailable") is not None

    # The AC starts advertising a heat mode -> assist can act, issue clears.
    hass.states.async_set(AC_ENTITY, "off", _AC_HEAT_DRY)
    await refresh(hass, init_integration)
    assert registry.async_get_issue(DOMAIN, "heating_assist_unavailable") is None


async def test_heating_assist_without_any_ac_raises(
    hass: HomeAssistant,
    living_area: str,
    register_entity_in_area: Callable[[str, str | None], str],
    entity_id_for: Callable[[str, str], str],
) -> None:
    """Assist on in a radiator-only home (no AC at all) is flagged too."""
    registry = ir.async_get(hass)
    entry = await _setup_trv_only(hass, living_area, register_entity_in_area)
    cid = entry.entry_id
    assert registry.async_get_issue(DOMAIN, "heating_assist_unavailable") is None

    await _turn_on(hass, entity_id_for, cid, "ac_heating_assist")
    await refresh(hass, entry)
    assert registry.async_get_issue(DOMAIN, "heating_assist_unavailable") is not None

    await _turn_off(hass, entity_id_for, cid, "ac_heating_assist")
    await refresh(hass, entry)
    assert registry.async_get_issue(DOMAIN, "heating_assist_unavailable") is None


async def test_offline_ac_does_not_falsely_flag_heating_assist(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """An AC that's merely offline has unknown modes, so assist isn't flagged.

    Its capabilities can't be read while unavailable; flagging then would be a
    false alarm every time the unit drops off the network.
    """
    registry = ir.async_get(hass)
    cid = init_integration.entry_id
    # A heat-capable AC that then goes offline.
    hass.states.async_set(AC_ENTITY, "off", _AC_HEAT_DRY)
    await _turn_on(hass, entity_id_for, cid, "ac_heating_assist")
    await refresh(hass, init_integration)
    assert registry.async_get_issue(DOMAIN, "heating_assist_unavailable") is None

    hass.states.async_set(AC_ENTITY, "unavailable")
    await refresh(hass, init_integration)
    assert registry.async_get_issue(DOMAIN, "heating_assist_unavailable") is None


async def test_dew_point_guard_without_dry_capable_ac_raises_and_clears(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
) -> None:
    """Dew-point guard (on by default) with a non-dry AC is flagged; dry clears.

    The fixture AC reports no modes, so the guard can't dehumidify through it.
    """
    registry = ir.async_get(hass)
    await refresh(hass, init_integration)
    assert registry.async_get_issue(DOMAIN, "dehumidify_unavailable") is not None

    hass.states.async_set(AC_ENTITY, "off", _AC_HEAT_DRY)
    await refresh(hass, init_integration)
    assert registry.async_get_issue(DOMAIN, "dehumidify_unavailable") is None


async def test_dew_point_guard_is_not_flagged_in_a_radiator_only_home(
    hass: HomeAssistant,
    living_area: str,
    register_entity_in_area: Callable[[str, str | None], str],
) -> None:
    """No AC configured means the guard has nothing to nag about (default on)."""
    registry = ir.async_get(hass)
    entry = await _setup_trv_only(hass, living_area, register_entity_in_area)
    await refresh(hass, entry)
    assert registry.async_get_issue(DOMAIN, "dehumidify_unavailable") is None


async def test_ac_ignore_window_without_an_ac_raises_and_clears(
    hass: HomeAssistant,
    living_area: str,
    register_entity_in_area: Callable[[str, str | None], str],
    entity_id_for: Callable[[str, str], str],
) -> None:
    """The own-room window exemption with no AC configured is inert -> flagged."""
    registry = ir.async_get(hass)
    entry = await _setup_trv_only(hass, living_area, register_entity_in_area)
    cid = entry.entry_id
    assert registry.async_get_issue(DOMAIN, "ac_ignore_window_inert") is None

    await _turn_on(hass, entity_id_for, cid, "ac_ignore_window")
    await refresh(hass, entry)
    assert registry.async_get_issue(DOMAIN, "ac_ignore_window_inert") is not None

    await _turn_off(hass, entity_id_for, cid, "ac_ignore_window")
    await refresh(hass, entry)
    assert registry.async_get_issue(DOMAIN, "ac_ignore_window_inert") is None


def _poorly_fitting_controller() -> MpcController:
    """A controller whose history the model structurally can't reproduce.

    Constant regressors with an alternating ±1 K change — exactly the
    signature of a weather-compensated radiator whose output the constant
    ``gain`` can't track. ``relative_fit_error`` sits at/above the threshold.
    """
    controller = MpcController(ThermalParams(gain=0.0, loss=0.0))
    for i in range(8):
        controller.history.append(
            Sample(
                dt=1.0,
                temp=21.0,
                next_temp=22.0 if i % 2 == 0 else 20.0,
                valve=0.5,
                outdoor=11.0,
            )
        )
    return controller


def _well_fitting_controller() -> MpcController:
    """A controller whose history its params reproduce exactly."""
    params = ThermalParams(gain=0.1, loss=0.01)
    controller = MpcController(params)
    for valve in (0.0, 0.5, 1.0, 0.2, 0.8, 0.6):
        temp, outdoor = 21.0, 5.0
        delta = params.gain * valve - params.loss * (temp - outdoor)
        controller.history.append(
            Sample(
                dt=1.0, temp=temp, next_temp=temp + delta, valve=valve, outdoor=outdoor
            )
        )
    return controller


async def test_persistent_poor_mpc_fit_raises_and_clears(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """A model that can't fit for over a day raises a repair; a good fit clears it.

    The debounce is exercised by pre-ageing ``poor_fit_since``; a fresh poor
    fit does *not* raise immediately.
    """
    registry = ir.async_get(hass)
    coordinator: SmartClimateCoordinator = init_integration.runtime_data
    issue_id = f"mpc_model_poor_fit_{TRV_ENTITY}"
    bad = _poorly_fitting_controller()

    # Poor, but only just now -> debounced, no issue yet.
    evaluate_mpc_fit(coordinator, TRV_ENTITY, bad)
    assert registry.async_get_issue(DOMAIN, issue_id) is None
    assert runtime(coordinator, TRV_ENTITY).poor_fit_since is not None

    # Pretend it has been poor for longer than the debounce window -> raised.
    runtime(coordinator, TRV_ENTITY).poor_fit_since = (
        time.monotonic() - MPC_POOR_FIT_SECONDS - 10.0
    )
    evaluate_mpc_fit(coordinator, TRV_ENTITY, bad)
    assert registry.async_get_issue(DOMAIN, issue_id) is not None

    # The model fits again -> the streak resets and the notice clears.
    evaluate_mpc_fit(coordinator, TRV_ENTITY, _well_fitting_controller())
    assert registry.async_get_issue(DOMAIN, issue_id) is None
    assert runtime(coordinator, TRV_ENTITY).poor_fit_since is None


async def test_ac_ignore_window_with_an_ac_is_not_flagged(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """With an AC configured the exemption has a target, so no repair."""
    registry = ir.async_get(hass)
    cid = init_integration.entry_id
    await _turn_on(hass, entity_id_for, cid, "ac_ignore_window")
    await refresh(hass, init_integration)
    assert registry.async_get_issue(DOMAIN, "ac_ignore_window_inert") is None


async def test_adaptive_comfort_without_outdoor_sensor_raises_and_clears(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """Enabling adaptive comfort with no outdoor sensor raises a repair issue."""
    registry = ir.async_get(hass)
    cid = init_integration.entry_id
    # No outdoor sensor configured, adaptive comfort off by default -> no issue.
    assert registry.async_get_issue(DOMAIN, "outdoor_sensor_missing") is None

    switch = entity_id_for("switch", f"{cid}_adaptive_cooling_comfort")
    await hass.services.async_call(
        "switch", "turn_on", {ATTR_ENTITY_ID: switch}, blocking=True
    )
    await refresh(hass, init_integration)
    assert registry.async_get_issue(DOMAIN, "outdoor_sensor_missing") is not None

    await hass.services.async_call(
        "switch", "turn_off", {ATTR_ENTITY_ID: switch}, blocking=True
    )
    await refresh(hass, init_integration)
    assert registry.async_get_issue(DOMAIN, "outdoor_sensor_missing") is None


async def test_inverted_band_raises_and_clears(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """Inverting a preset's edges (via the number entities) raises the issue.

    The climate ``set_temperature`` service rejects low > high, so the real way
    a user can invert a band is by editing the independent per-preset heat/cool
    number entities.
    """
    registry = ir.async_get(hass)
    assert registry.async_get_issue(DOMAIN, "inverted_band") is None
    cid = init_integration.entry_id
    heat_num = entity_id_for("number", f"{cid}_preset_home_heat")
    cool_num = entity_id_for("number", f"{cid}_preset_home_cool")

    async def _set(entity: str, value: float) -> None:
        await hass.services.async_call(
            "number",
            "set_value",
            {ATTR_ENTITY_ID: entity, "value": value},
            blocking=True,
        )

    # Push the cool edge below the heat edge -> inverted (no neutral zone).
    await _set(cool_num, 22.0)
    await _set(heat_num, 24.0)
    await refresh(hass, init_integration)
    assert registry.async_get_issue(DOMAIN, "inverted_band") is not None

    # Restore a sane band -> the issue clears.
    await _set(heat_num, 20.5)
    await _set(cool_num, 24.5)
    await refresh(hass, init_integration)
    assert registry.async_get_issue(DOMAIN, "inverted_band") is None


async def test_no_temperature_source_raises_issue(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Losing every temperature source raises the no-source repair issue."""
    registry = ir.async_get(hass)
    assert registry.async_get_issue(DOMAIN, "no_temperature_source") is None

    for entity in (TRV_ENTITY, AC_ENTITY, AREA_TEMP_SENSOR, AREA_HUMIDITY_SENSOR):
        hass.states.async_set(entity, STATE_UNAVAILABLE)
    await refresh(hass, init_integration)

    assert registry.async_get_issue(DOMAIN, "no_temperature_source") is not None


async def test_repeated_control_failures_raise_and_clear(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A repeatedly failing control cycle raises a repair; success clears it."""
    registry = ir.async_get(hass)
    coordinator: SmartClimateCoordinator = init_integration.runtime_data

    async def _boom(_data: object) -> None:
        raise RuntimeError

    monkeypatch.setattr(coordinator, "_async_control", _boom)
    # One failure short of the threshold: contained, no repair yet.
    for _ in range(CONTROL_FAILURE_ISSUE_THRESHOLD - 1):
        await refresh(hass, init_integration)
    assert registry.async_get_issue(DOMAIN, "control_loop_failing") is None

    # The threshold-th consecutive failure surfaces the repair.
    await refresh(hass, init_integration)
    assert registry.async_get_issue(DOMAIN, "control_loop_failing") is not None

    # The next clean cycle clears it (and resets the counter).
    monkeypatch.undo()
    await refresh(hass, init_integration)
    assert registry.async_get_issue(DOMAIN, "control_loop_failing") is None
