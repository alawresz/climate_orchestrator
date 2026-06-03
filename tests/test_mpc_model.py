"""Tests for the thermal model and system identification."""

from __future__ import annotations

import numpy as np

from custom_components.climate_orchestrator.control.mpc.model import (
    DEFAULT_PARAMS,
    Sample,
    ThermalParams,
    identify_parameters,
    predict_step,
)


def test_identify_recovers_known_parameters() -> None:
    """Fitting noisy transitions recovers the true gain and loss."""
    true = ThermalParams(gain=0.20, loss=0.02)
    rng = np.random.default_rng(0)
    samples: list[Sample] = []
    temp, outdoor, dt = 18.0, 5.0, 1.0
    for _ in range(60):
        valve = float(rng.uniform(0.0, 1.0))
        nxt = predict_step(temp, valve, outdoor, true, dt) + float(
            rng.normal(0.0, 0.005)
        )
        samples.append(
            Sample(dt=dt, temp=temp, next_temp=nxt, valve=valve, outdoor=outdoor)
        )
        temp = nxt

    est = identify_parameters(samples)
    assert abs(est.gain - true.gain) < 0.03
    assert abs(est.loss - true.loss) < 0.015


def test_identify_returns_prior_when_too_few_samples() -> None:
    """With too little data we keep the prior rather than overfit."""
    one = [Sample(dt=1.0, temp=20.0, next_temp=20.5, valve=1.0, outdoor=5.0)]
    assert identify_parameters(one) is DEFAULT_PARAMS
