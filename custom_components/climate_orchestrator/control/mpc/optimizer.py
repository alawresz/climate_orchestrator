"""Receding-horizon valve optimization.

Picks the valve fraction that minimises predicted tracking error over a short
horizon (with an optional control-effort penalty), bounded to the valve's range
(docs/internals/mpc.md). A single held move is optimised per cycle, which suits a TRV
that keeps its opening until the next update. Pure.
"""

from __future__ import annotations

from collections.abc import Sequence

from scipy.optimize import minimize_scalar

from ..numeric import clamp
from .model import ThermalParams, predict_step

DEFAULT_HORIZON = 6
DEFAULT_EFFORT_WEIGHT = 0.0

# ``outdoor`` may be a single held temperature or a per-step forecast series.
Outdoor = float | Sequence[float]


def _outdoor_at(outdoor: Outdoor, step: int) -> float:
    """Outdoor temperature for a rollout step (held flat past a series' end)."""
    if isinstance(outdoor, Sequence):
        idx = step if step < len(outdoor) else len(outdoor) - 1
        return float(outdoor[idx])
    return float(outdoor)


def _rollout_cost(
    temp0: float,
    valve: float,
    target: float,
    outdoor: Outdoor,
    params: ThermalParams,
    dt: float,
    horizon: int,
    effort_weight: float,
) -> float:
    """Sum of squared tracking error over the horizon, plus effort."""
    temp = temp0
    cost = 0.0
    for step in range(horizon):
        temp = predict_step(temp, valve, _outdoor_at(outdoor, step), params, dt)
        cost += (temp - target) ** 2
    return cost + effort_weight * valve * valve


def optimize_valve(
    temp0: float,
    target: float,
    outdoor: Outdoor,
    params: ThermalParams,
    *,
    dt: float,
    horizon: int = DEFAULT_HORIZON,
    max_opening: float = 1.0,
    effort_weight: float = DEFAULT_EFFORT_WEIGHT,
) -> float:
    """Return the optimal valve fraction in ``[0, max_opening]``.

    ``outdoor`` is either a constant temperature or a per-step forecast series
    (e.g. for forecast-based preconditioning); a series shorter than the horizon
    holds its last value.
    """
    if max_opening <= 0.0:
        return 0.0
    result = minimize_scalar(
        lambda valve: _rollout_cost(
            temp0, valve, target, outdoor, params, dt, horizon, effort_weight
        ),
        bounds=(0.0, max_opening),
        method="bounded",
    )
    return float(clamp(result.x, 0.0, max_opening))
