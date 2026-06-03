"""Pure tests: forecast expansion + the MPC optimizer with an outdoor series."""

from __future__ import annotations

import pytest

from custom_components.climate_orchestrator.control.forecast import expand_forecast
from custom_components.climate_orchestrator.control.mpc.model import ThermalParams
from custom_components.climate_orchestrator.control.mpc.optimizer import optimize_valve


def test_expand_forecast_hourly_steps() -> None:
    """An hourly step grid returns the hourly values verbatim."""
    assert expand_forecast([10.0, 20.0], 60.0, 2) == [10.0, 20.0]


def test_expand_forecast_interpolates_sub_hourly() -> None:
    """Half-hour steps linearly interpolate between hourly points."""
    assert expand_forecast([10.0, 20.0], 30.0, 3) == [10.0, 15.0, 20.0]


def test_expand_forecast_holds_last_value() -> None:
    """Beyond the forecast's end the last value is held flat."""
    assert expand_forecast([10.0, 20.0], 60.0, 4) == [10.0, 20.0, 20.0, 20.0]


def test_expand_forecast_empty_inputs() -> None:
    """No forecast, no steps, or a non-positive step yields an empty series."""
    assert expand_forecast([], 60.0, 3) == []
    assert expand_forecast([10.0], 60.0, 0) == []
    assert expand_forecast([10.0, 20.0], 0.0, 3) == []


_PARAMS = ThermalParams(gain=0.1, loss=0.05)


def test_optimizer_accepts_constant_series_like_scalar() -> None:
    """A constant series gives the same valve as the equivalent scalar."""
    scalar = optimize_valve(19.0, 21.0, 20.0, _PARAMS, dt=5.0, horizon=12)
    series = optimize_valve(19.0, 21.0, [20.0] * 12, _PARAMS, dt=5.0, horizon=12)
    assert series == pytest.approx(scalar, abs=1e-3)


def test_colder_forecast_opens_the_valve_more() -> None:
    """A forecast that turns colder pre-heats: a larger valve than holding warm."""
    warm = optimize_valve(19.0, 21.0, 20.0, _PARAMS, dt=5.0, horizon=12)
    cooling = [20.0 - k for k in range(12)]  # drops 1 K per step
    colder = optimize_valve(19.0, 21.0, cooling, _PARAMS, dt=5.0, horizon=12)
    assert colder > warm


# --- mutation-hardening: boundary/exact-value pins (mutmut survivors) ---


def test_expand_forecast_single_step() -> None:
    assert expand_forecast([10.0, 20.0], 60.0, 1) == [10.0]


def test_expand_forecast_interpolates_across_later_hours() -> None:
    """Interpolation must work past the first hourly segment."""
    assert expand_forecast([10.0, 20.0, 30.0], 30.0, 5) == [
        10.0,
        15.0,
        20.0,
        25.0,
        30.0,
    ]


def test_expand_forecast_subminute_steps() -> None:
    """Step sizes in (0, 1] minutes are valid, not treated as disabled."""
    series = expand_forecast([10.0, 20.0], 0.5, 2)
    assert series[0] == 10.0
    assert series[1] == pytest.approx(10.0833333, abs=1e-6)
