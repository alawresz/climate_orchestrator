"""First-order thermal model and online system identification.

Room dynamics are modelled as a single RC node::

    T[n+1] = T[n] + dt * (gain * valve - loss * (T[n] - outdoor))

where ``valve`` is the heat input fraction in [0, 1]. Parameters are fitted from
observed transitions with ``scipy.optimize.least_squares`` and regularised
toward a prior so a cold start stays sane (docs/internals/mpc.md). Pure: numpy/scipy.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import TYPE_CHECKING

import numpy as np
from scipy.optimize import least_squares

from ...const import MPC_MIN_SAMPLES as MIN_SAMPLES

if TYPE_CHECKING:
    from collections.abc import Sequence

# Cold-start priors and fit settings. ``MIN_SAMPLES`` lives in ``const``
# (scipy-free) so the sensor platform can read it without importing this
# numpy/scipy-laden module; imported here under its local name for the fit.
DEFAULT_GAIN = 0.10
DEFAULT_LOSS = 0.01
_PRIOR_WEIGHT = 0.05
# Physical sanity bounds for the fit. A radiator gaining 2 K/min at full valve
# or a room with a 1-minute thermal time constant is already absurd; anything
# the solver pushes past these is degenerate data, not physics. Finite bounds
# also keep the optimiser's rollout from overflowing on runaway parameters.
MAX_GAIN = 2.0  # K per minute at full valve
MAX_LOSS = 1.0  # 1/minute coupling to the outdoor delta


@dataclass(frozen=True, slots=True)
class ThermalParams:
    """Identified room dynamics."""

    gain: float  # K per minute at full valve
    loss: float  # 1/minute coupling to the outdoor delta


DEFAULT_PARAMS = ThermalParams(gain=DEFAULT_GAIN, loss=DEFAULT_LOSS)


@dataclass(frozen=True, slots=True)
class Sample:
    """One observed transition used for identification."""

    dt: float
    temp: float
    next_temp: float
    valve: float
    outdoor: float


def predict_step(
    temp: float, valve: float, outdoor: float, params: ThermalParams, dt: float
) -> float:
    """Advance the room temperature one step under a held valve fraction."""
    return temp + dt * (params.gain * valve - params.loss * (temp - outdoor))


def identify_parameters(
    samples: Sequence[Sample], prior: ThermalParams = DEFAULT_PARAMS
) -> ThermalParams:
    """Fit ``(gain, loss)`` from transitions; return the prior if too few."""
    if len(samples) < MIN_SAMPLES:
        return prior

    dt = np.array([s.dt for s in samples])
    temp = np.array([s.temp for s in samples])
    valve = np.array([s.valve for s in samples])
    outdoor = np.array([s.outdoor for s in samples])
    observed = np.array([s.next_temp - s.temp for s in samples])

    def residuals(x: np.ndarray) -> np.ndarray:
        gain, loss = x
        predicted = dt * (gain * valve - loss * (temp - outdoor))
        regularization = np.array(
            [_PRIOR_WEIGHT * (gain - prior.gain), _PRIOR_WEIGHT * (loss - prior.loss)]
        )
        return np.concatenate([predicted - observed, regularization])

    result = least_squares(
        residuals,
        # x0 must lie inside the bounds, whatever a restored prior claims.
        x0=np.array([min(prior.gain, MAX_GAIN), min(prior.loss, MAX_LOSS)]),
        bounds=([0.0, 0.0], [MAX_GAIN, MAX_LOSS]),
    )
    gain, loss = float(result.x[0]), float(result.x[1])
    if not result.success or not (math.isfinite(gain) and math.isfinite(loss)):
        # Degenerate data (all-identical samples, NaN creep) can make the
        # solver give up or return garbage — keep the last good parameters.
        return prior
    return ThermalParams(gain=gain, loss=loss)
