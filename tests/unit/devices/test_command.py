"""Tests for building device commands from engine decisions."""

from __future__ import annotations

from custom_components.climate_orchestrator.control.engine import (
    DeviceDecision,
    DeviceKind,
)
from custom_components.climate_orchestrator.control.hysteresis import Demand
from custom_components.climate_orchestrator.devices.command import build_command
from custom_components.climate_orchestrator.devices.model import (
    AdapterCapabilities,
    Mode,
)
from custom_components.climate_orchestrator.models import Band

CAPS = AdapterCapabilities(
    can_heat=True,
    can_cool=True,
    can_dry=True,
    min_temp=16.0,
    max_temp=30.0,
    target_step=0.5,
)
BAND = Band(heat_edge=20.0, cool_edge=24.0)  # target 22.0


def _decision(demand: Demand, *, dry: bool = False) -> DeviceDecision:
    return DeviceDecision(key="x", demand=demand, dry_mode=dry, reason="")


def test_heater_heats_to_edge_plus_tolerance() -> None:
    cmd = build_command(
        _decision(Demand.HEAT),
        DeviceKind.HEATER,
        band=BAND,
        ac_setpoint_bias=1.5,
        caps=CAPS,
        tolerance=0.5,
    )
    assert cmd.hvac_mode is Mode.HEAT
    assert cmd.target_temp == 20.5  # heat_edge 20 + tolerance 0.5


def test_heater_idle_turns_off() -> None:
    cmd = build_command(
        _decision(Demand.IDLE),
        DeviceKind.HEATER,
        band=BAND,
        ac_setpoint_bias=1.5,
        caps=CAPS,
    )
    assert cmd.hvac_mode is Mode.OFF


def test_cooler_cools_below_edge_target_by_bias() -> None:
    cmd = build_command(
        _decision(Demand.COOL),
        DeviceKind.COOLER,
        band=BAND,
        ac_setpoint_bias=1.5,
        caps=CAPS,
        tolerance=0.5,
    )
    assert cmd.hvac_mode is Mode.COOL
    assert cmd.target_temp == 22.0  # cool_target (24 - 0.5) - bias 1.5


def test_cooler_heats_to_edge_when_assist_yields_heat() -> None:
    """An AC told to HEAT (assist) drives to the heat target like a TRV."""
    cmd = build_command(
        _decision(Demand.HEAT),
        DeviceKind.COOLER,
        band=BAND,
        ac_setpoint_bias=1.5,
        caps=CAPS,
        tolerance=0.5,
    )
    assert cmd.hvac_mode is Mode.HEAT
    assert cmd.target_temp == 20.5  # heat_edge 20 + tolerance 0.5


def test_cooler_heat_off_without_capability() -> None:
    """An AC that can't heat stays off even on a HEAT demand."""
    caps = AdapterCapabilities(
        can_heat=False,
        can_cool=True,
        can_dry=True,
        min_temp=16.0,
        max_temp=30.0,
        target_step=0.5,
    )
    cmd = build_command(
        _decision(Demand.HEAT),
        DeviceKind.COOLER,
        band=BAND,
        ac_setpoint_bias=1.5,
        caps=caps,
    )
    assert cmd.hvac_mode is Mode.OFF


def test_cooler_runs_dry_under_guard() -> None:
    cmd = build_command(
        _decision(Demand.IDLE, dry=True),
        DeviceKind.COOLER,
        band=BAND,
        ac_setpoint_bias=1.5,
        caps=CAPS,
    )
    assert cmd.hvac_mode is Mode.DRY


def test_cooler_setpoint_anchored_below_ac_internal_temp() -> None:
    """When the AC's own sensor reads cold, the setpoint is driven below it."""
    # cool_target (24 - 0.5 = 23.5) - bias 1.5 = 22.0 would sit ABOVE the AC's
    # internal 21.0, so it'd just fan. Anchor pulls it to 21.0 - 1.0 kick = 20.0.
    cmd = build_command(
        _decision(Demand.COOL),
        DeviceKind.COOLER,
        band=BAND,
        ac_setpoint_bias=1.5,
        caps=CAPS,
        tolerance=0.5,
        device_current_temp=21.0,
    )
    assert cmd.hvac_mode is Mode.COOL
    assert cmd.target_temp == 20.0


def test_cooler_drive_scales_with_room_above_target() -> None:
    """The hotter the room above target, the deeper below the AC's own sensor."""
    # cool_target 23.5; room 26.5 -> 3.0 above target. AC internal 21.0.
    # setpoint = min(23.5 - 1.5, 21.0 - max(3.0, 1.0)) = min(22.0, 18.0) = 18.0.
    cmd = build_command(
        _decision(Demand.COOL),
        DeviceKind.COOLER,
        band=BAND,
        ac_setpoint_bias=1.5,
        caps=CAPS,
        tolerance=0.5,
        device_current_temp=21.0,
        room_temp=26.5,
    )
    assert cmd.target_temp == 18.0


def test_cooler_bias_clamped_up_to_min_temp() -> None:
    """A large bias can't push the AC below its accepted minimum."""
    cmd = build_command(
        _decision(Demand.COOL),
        DeviceKind.COOLER,
        band=BAND,  # cool_target (24 - 0.5) = 23.5
        ac_setpoint_bias=10.0,  # 23.5 - 10 = 13.5, under the 16.0 minimum
        caps=CAPS,
        tolerance=0.5,
    )
    assert cmd.target_temp == 16.0  # clamped up to min_temp


def test_heater_clamped_down_to_max_temp() -> None:
    """A heat target above the device maximum is clamped down."""
    caps = AdapterCapabilities(
        can_heat=True,
        can_cool=False,
        can_dry=False,
        min_temp=7.0,
        max_temp=21.0,
        target_step=0.5,
    )
    cmd = build_command(
        _decision(Demand.HEAT),
        DeviceKind.HEATER,
        band=Band(heat_edge=23.0, cool_edge=27.0),  # heat_target 23.5
        ac_setpoint_bias=0.0,
        caps=caps,
        tolerance=0.5,
    )
    assert cmd.target_temp == 21.0  # clamped down to max_temp
