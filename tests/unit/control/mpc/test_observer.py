"""Tests for the Kalman observer."""

from __future__ import annotations

import numpy as np
import pytest

from custom_components.climate_orchestrator.control.mpc.model import ThermalParams
from custom_components.climate_orchestrator.control.mpc.observer import (
    KalmanState,
    predict,
    update,
)


def test_observer_converges_to_truth_and_shrinks_variance() -> None:
    """Filtering noisy measurements of a steady temperature converges."""
    # No dynamics: temperature is constant, so prediction holds it steady.
    static = ThermalParams(gain=0.0, loss=0.0)
    state = KalmanState(temp=20.0, variance=1.0)
    rng = np.random.default_rng(1)
    truth = 21.0

    for _ in range(60):
        state = predict(state, valve=0.0, outdoor=truth, params=static, dt=1.0)
        state = update(state, truth + float(rng.normal(0.0, 0.1)))

    assert abs(state.temp - truth) < 0.2
    assert state.variance < 1.0


# --- mutation-hardening: boundary/exact-value pins (mutmut survivors) ---


def test_kalman_predict_variance() -> None:
    state = KalmanState(temp=20.0, variance=1.0)
    out = predict(
        state,
        valve=0.0,
        outdoor=20.0,
        params=ThermalParams(gain=0.1, loss=0.01),
        dt=1.0,
    )
    assert out.temp == pytest.approx(20.0, abs=1e-12)
    # jac = 1 - dt*loss = 0.99; var = jac^2 * 1.0 + 0.01
    assert out.variance == pytest.approx(0.9901, abs=1e-12)


def test_kalman_update_gain_and_variance() -> None:
    out = update(KalmanState(temp=20.0, variance=0.04), 21.0)
    # gain = 0.04 / (0.04 + 0.04) = 0.5
    assert out.temp == pytest.approx(20.5, abs=1e-12)
    assert out.variance == pytest.approx(0.02, abs=1e-12)
