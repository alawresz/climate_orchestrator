"""Tests for the MPC fit-residual (model confidence) metric."""

from __future__ import annotations

import pytest

from custom_components.climate_orchestrator.control.mpc.controller import MpcController
from custom_components.climate_orchestrator.control.mpc.model import (
    Sample,
    ThermalParams,
)


def test_fit_rmse_none_until_enough_samples() -> None:
    """With too little history there's no fitted model to score."""
    assert MpcController().fit_rmse() is None


def test_fit_rmse_zero_for_a_perfect_fit() -> None:
    """History generated exactly by the params yields ~zero residual."""
    params = ThermalParams(gain=0.1, loss=0.01)
    controller = MpcController(params)
    for valve in (0.0, 0.5, 1.0, 0.2, 0.8, 0.6):
        temp, outdoor = 21.0, 5.0
        delta = params.gain * valve - params.loss * (temp - outdoor)
        controller.history.append(
            Sample(
                dt=1.0,
                temp=temp,
                next_temp=temp + delta,
                valve=valve,
                outdoor=outdoor,
            )
        )
    assert controller.fit_rmse() == pytest.approx(0.0, abs=1e-9)


def test_fit_rmse_positive_when_model_misfits() -> None:
    """A model that doesn't explain the data has a non-zero residual."""
    controller = MpcController(ThermalParams(gain=0.1, loss=0.01))
    for valve in (0.0, 0.5, 1.0, 0.2, 0.8, 0.6):
        # Observed change deliberately inconsistent with the params.
        controller.history.append(
            Sample(dt=1.0, temp=21.0, next_temp=24.0, valve=valve, outdoor=5.0)
        )
    rmse = controller.fit_rmse()
    assert rmse is not None
    assert rmse > 0.0
