"""End-to-end tests for the MPC controller on a synthetic room."""

from __future__ import annotations

import math

import pytest

from custom_components.climate_orchestrator.control.mpc.controller import MpcController
from custom_components.climate_orchestrator.control.mpc.model import (
    Sample,
    ThermalParams,
    predict_step,
)


def test_controller_drives_temperature_to_target() -> None:
    """Closed loop on a simulated room converges near the target."""
    true = ThermalParams(gain=0.25, loss=0.02)  # equilibrium reachable
    controller = MpcController()

    temp, outdoor, target, dt, valve = 17.0, 15.0, 21.0, 1.0, 0.0
    for _ in range(200):
        controller.observe(temp=temp, valve=valve, outdoor=outdoor, dt=dt)
        valve = (
            controller.compute_valve_pct(
                temp=temp, target=target, outdoor=outdoor, dt=dt
            )
            / 100.0
        )
        temp = predict_step(temp, valve, outdoor, true, dt)

    assert abs(temp - target) < 0.7


def test_persistence_round_trip() -> None:
    """Learned state survives a serialise/restore cycle."""
    controller = MpcController(ThermalParams(gain=0.3, loss=0.03))
    controller.observe(temp=18.0, valve=1.0, outdoor=5.0, dt=1.0)
    controller.observe(temp=18.4, valve=1.0, outdoor=5.0, dt=1.0)

    restored = MpcController.from_dict(controller.to_dict())
    assert restored.params == controller.params
    assert len(restored.history) == len(controller.history)


# --- mutation-hardening: boundary/exact-value pins (mutmut survivors) ---


def test_compute_valve_pct_full_demand_and_ceiling() -> None:
    c = MpcController()
    assert c.compute_valve_pct(temp=15.0, target=25.0, outdoor=15.0, dt=5.0) == 100.0
    assert (
        c.compute_valve_pct(
            temp=15.0, target=25.0, outdoor=15.0, dt=5.0, max_opening_pct=50.0
        )
        == 50.0
    )


def test_compute_valve_pct_horizon_and_rounding() -> None:
    c = MpcController()
    short = c.compute_valve_pct(temp=20.0, target=20.2, outdoor=20.0, dt=5.0, horizon=1)
    long = c.compute_valve_pct(temp=20.0, target=20.2, outdoor=20.0, dt=5.0)
    assert short == 40.0
    assert long == 10.3  # one-decimal rounding of ~10.2787
    assert isinstance(short, float)


def test_history_is_bounded_by_max_history() -> None:
    c = MpcController(max_history=3)
    for k in range(5):
        c.observe(temp=20.0 + k * 0.1, valve=0.5, outdoor=10.0, dt=1.0)
    assert len(c.history) == 3


def test_observe_requires_strictly_positive_dt() -> None:
    c = MpcController()
    c.observe(temp=20.0, valve=0.5, outdoor=10.0, dt=0.0)
    c.observe(temp=20.1, valve=0.5, outdoor=10.0, dt=0.0)
    assert len(c.history) == 0
    c2 = MpcController()
    c2.observe(temp=20.0, valve=0.5, outdoor=10.0, dt=0.5)
    c2.observe(temp=20.1, valve=0.5, outdoor=10.0, dt=0.5)
    assert len(c2.history) == 1


def test_observe_fits_at_exactly_min_samples() -> None:
    """The 6th sample triggers identification (>=, not >)."""
    c = MpcController()
    temp = 20.0
    for _ in range(7):
        c.observe(temp=temp, valve=1.0, outdoor=temp, dt=1.0)
        temp += 0.3  # pure gain 0.3 signal (loss term zeroed via outdoor==temp)
    assert len(c.history) == 6
    assert c.params.gain == pytest.approx(0.3, abs=0.05)


def test_observe_passes_current_params_as_prior() -> None:
    """Neutral data keeps the controller's own (custom) prior, not the default."""
    c = MpcController(ThermalParams(gain=0.3, loss=0.07))
    for _ in range(7):
        c.observe(temp=20.0, valve=0.0, outdoor=20.0, dt=1.0)
    assert c.params.gain == pytest.approx(0.3, abs=0.02)
    assert c.params.loss == pytest.approx(0.07, abs=0.02)


def test_fit_rmse_exact_value() -> None:
    c = MpcController(ThermalParams(gain=0.1, loss=0.0))
    deltas = [0.1, 0.2, 0.3, 0.1, 0.2, 0.3]
    temp = 20.0
    for d in deltas:
        c.history.append(
            Sample(dt=1.0, temp=temp, next_temp=temp + d, valve=0.0, outdoor=temp)
        )
        temp += d
    assert c.fit_rmse() == pytest.approx(
        math.sqrt(sum(d * d for d in deltas) / 6), abs=1e-9
    )
