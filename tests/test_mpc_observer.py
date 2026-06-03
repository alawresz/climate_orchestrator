"""Tests for the Kalman observer."""

from __future__ import annotations

import numpy as np

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
