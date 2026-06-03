"""Tests for the receding-horizon valve optimizer."""

from __future__ import annotations

import pytest

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


# --- mutation-hardening: boundary/exact-value pins (mutmut survivors) ---


_P = ThermalParams(gain=0.1, loss=0.01)


def test_optimizer_default_bound_is_one() -> None:
    assert optimize_valve(15.0, 25.0, 15.0, _P, dt=5.0, horizon=6) == pytest.approx(
        1.0, abs=1e-3
    )


def test_optimizer_zero_bound_returns_closed() -> None:
    assert (
        optimize_valve(15.0, 25.0, 15.0, _P, dt=5.0, horizon=6, max_opening=0.0) == 0.0
    )


def test_optimizer_effort_weight_penalises_opening() -> None:
    free = optimize_valve(20.0, 20.2, 20.0, _P, dt=5.0, horizon=1)
    costly = optimize_valve(20.0, 20.2, 20.0, _P, dt=5.0, horizon=1, effort_weight=2.0)
    assert free == pytest.approx(0.4, abs=1e-3)
    assert costly < free - 0.1


def test_optimizer_holds_forecast_tail_value() -> None:
    """A short forecast holds its LAST value beyond the end of the series."""
    warm_held = optimize_valve(19.0, 21.0, 25.0, _P, dt=5.0, horizon=6)
    cold_tail = optimize_valve(19.0, 21.0, [25.0, 5.0], _P, dt=5.0, horizon=6)
    assert cold_tail > warm_held + 0.3
