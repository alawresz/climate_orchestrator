"""Scalar Kalman filter for room temperature.

Forward-predicts the room temperature between sensor updates using the thermal
model, and corrects on each measurement. Smooths noisy sensors and bridges
slow-reporting devices (docs/internals/mpc.md). Pure.
"""

from __future__ import annotations

from dataclasses import dataclass

from .model import ThermalParams, predict_step

# Default process/measurement variances (tunable later).
PROCESS_VAR = 0.01
MEASUREMENT_VAR = 0.04
# Variance ceiling: a 5 K standard deviation already means "the estimate is
# worthless, trust the next measurement almost entirely" (Kalman gain ~0.998).
# Without a ceiling, a long prediction gap or corrupt restored state can grow
# the variance without bound and destabilise subsequent updates.
MAX_VARIANCE = 25.0


@dataclass(frozen=True, slots=True)
class KalmanState:
    """Estimated temperature and its variance."""

    temp: float
    variance: float


def predict(
    state: KalmanState,
    valve: float,
    outdoor: float,
    params: ThermalParams,
    dt: float,
    *,
    process_var: float = PROCESS_VAR,
) -> KalmanState:
    """Project the estimate forward one step under a held valve."""
    temp = predict_step(state.temp, valve, outdoor, params, dt)
    # Jacobian of the model w.r.t. temperature.
    jac = 1.0 - dt * params.loss
    variance = min(jac * state.variance * jac + process_var, MAX_VARIANCE)
    return KalmanState(temp=temp, variance=variance)


def update(
    state: KalmanState,
    measurement: float,
    *,
    measurement_var: float = MEASUREMENT_VAR,
) -> KalmanState:
    """Correct the estimate with a new measurement."""
    gain = state.variance / (state.variance + measurement_var)
    temp = state.temp + gain * (measurement - state.temp)
    variance = (1.0 - gain) * state.variance
    return KalmanState(temp=temp, variance=variance)
