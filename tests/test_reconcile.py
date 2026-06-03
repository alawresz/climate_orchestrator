"""Tests for update-minimising reconcile logic."""

from __future__ import annotations

from custom_components.climate_orchestrator.devices.model import (
    DeviceCommand,
    DeviceState,
    Mode,
)
from custom_components.climate_orchestrator.devices.reconcile import reconcile


def _state(mode: str | None, target: float | None) -> DeviceState:
    return DeviceState(
        available=True, hvac_mode=mode, current_temp=None, target_temp=target
    )


def test_no_writes_when_already_in_state() -> None:
    """Matching mode and target produces no service calls."""
    writes = reconcile(_state("heat", 22.0), DeviceCommand(Mode.HEAT, 22.0), step=0.5)
    assert writes.is_empty


def test_mode_and_temperature_change_emitted() -> None:
    """A mode change carries the target too."""
    writes = reconcile(_state("off", None), DeviceCommand(Mode.HEAT, 22.0), step=0.5)
    assert writes.set_hvac_mode is Mode.HEAT
    assert writes.set_temperature == 22.0


def test_sub_step_temperature_change_skipped() -> None:
    """A target change smaller than the device step is not written."""
    writes = reconcile(_state("heat", 22.0), DeviceCommand(Mode.HEAT, 22.2), step=0.5)
    assert writes.set_temperature is None


def test_large_temperature_change_emitted() -> None:
    """A target change of at least one step is written."""
    writes = reconcile(_state("heat", 22.0), DeviceCommand(Mode.HEAT, 23.0), step=0.5)
    assert writes.set_temperature == 23.0


def test_off_command_skips_temperature() -> None:
    """Turning off never sets a temperature."""
    writes = reconcile(_state("heat", 22.0), DeviceCommand(Mode.OFF, None), step=0.5)
    assert writes.set_hvac_mode is Mode.OFF
    assert writes.set_temperature is None


def test_change_at_step_boundary_is_written() -> None:
    """A change of exactly one step is written (>= step)."""
    writes = reconcile(_state("heat", 22.0), DeviceCommand(Mode.HEAT, 22.5), step=0.5)
    assert writes.set_temperature == 22.5
