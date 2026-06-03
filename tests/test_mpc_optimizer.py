"""Tests for the receding-horizon valve optimizer."""

from __future__ import annotations

from custom_components.climate_orchestrator.control.mpc.model import ThermalParams
from custom_components.climate_orchestrator.control.mpc.optimizer import optimize_valve

PARAMS = ThermalParams(gain=0.25, loss=0.02)


def test_cold_room_opens_the_valve() -> None:
    """Well below target, the optimiser opens the valve wide."""
    valve = optimize_valve(16.0, 21.0, 15.0, PARAMS, dt=1.0, horizon=10)
    assert valve > 0.5


def test_warm_room_closes_the_valve() -> None:
    """Above target (heating only cools by drifting), the valve closes."""
    valve = optimize_valve(23.0, 21.0, 15.0, PARAMS, dt=1.0, horizon=10)
    assert valve < 0.1


def test_respects_max_opening() -> None:
    """The result never exceeds the allowed maximum opening."""
    valve = optimize_valve(16.0, 21.0, 5.0, PARAMS, dt=1.0, horizon=10, max_opening=0.3)
    assert valve <= 0.3 + 1e-9


def test_zero_max_opening_returns_zero() -> None:
    """A clamped-shut valve yields zero with no optimisation."""
    assert optimize_valve(16.0, 21.0, 5.0, PARAMS, dt=1.0, max_opening=0.0) == 0.0
