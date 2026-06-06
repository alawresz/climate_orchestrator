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


def test_relative_fit_error_none_until_enough_samples() -> None:
    """Too little history -> no judgeable fit."""
    assert MpcController().relative_fit_error() is None


def test_relative_fit_error_near_zero_for_a_perfect_fit() -> None:
    """A model that reproduces the data explains ~all of the movement."""
    params = ThermalParams(gain=0.1, loss=0.01)
    controller = MpcController(params)
    for valve in (0.0, 0.5, 1.0, 0.2, 0.8, 0.6):
        temp, outdoor = 21.0, 5.0
        delta = params.gain * valve - params.loss * (temp - outdoor)
        controller.history.append(
            Sample(
                dt=1.0, temp=temp, next_temp=temp + delta, valve=valve, outdoor=outdoor
            )
        )
    error = controller.relative_fit_error()
    assert error is not None
    assert error == pytest.approx(0.0, abs=1e-6)


def test_relative_fit_error_near_one_when_model_explains_nothing() -> None:
    """Constant regressors but alternating change: the model can't do better
    than predicting no change, so the relative error sits around 1."""
    controller = MpcController(ThermalParams(gain=0.0, loss=0.0))
    for i in range(8):
        # Same valve and (temp - outdoor) every step, but the room lurches
        # +1 / -1 K alternately — uncorrelated with anything the model sees.
        controller.history.append(
            Sample(
                dt=1.0,
                temp=21.0,
                next_temp=22.0 if i % 2 == 0 else 20.0,
                valve=0.5,
                outdoor=11.0,
            )
        )
    error = controller.relative_fit_error()
    assert error is not None
    assert error >= 0.8  # at/above the poor-fit threshold


def test_relative_fit_error_none_for_a_static_room() -> None:
    """A room barely moving is noise-dominated -> fit quality is unjudgeable."""
    controller = MpcController(ThermalParams(gain=0.1, loss=0.01))
    for valve in (0.0, 0.5, 1.0, 0.2, 0.8, 0.6):
        # Essentially no temperature change between samples.
        controller.history.append(
            Sample(dt=1.0, temp=21.0, next_temp=21.0, valve=valve, outdoor=5.0)
        )
    assert controller.relative_fit_error() is None
