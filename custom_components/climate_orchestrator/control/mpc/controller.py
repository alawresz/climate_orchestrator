"""The MPC controller: learn the room, then optimise the valve.

Each cycle the controller observes the latest transition (feeding online system
identification) and computes the valve opening for the next interval. Its
learned state is serialisable so it survives restarts (DESIGN.md §9, §13). Pure.
"""

from __future__ import annotations

from collections import deque
from dataclasses import asdict
import math
from typing import TYPE_CHECKING, Any

from .model import (
    DEFAULT_PARAMS,
    MIN_SAMPLES,
    Sample,
    ThermalParams,
    identify_parameters,
)
from .optimizer import DEFAULT_HORIZON, optimize_valve

if TYPE_CHECKING:
    from collections.abc import Sequence

DEFAULT_MAX_HISTORY = 200


class MpcController:
    """Stateful per-room controller (learns parameters, optimises the valve)."""

    def __init__(
        self,
        params: ThermalParams = DEFAULT_PARAMS,
        *,
        max_history: int = DEFAULT_MAX_HISTORY,
    ) -> None:
        """Create a controller with optional starting parameters."""
        self.params = params
        self.history: deque[Sample] = deque(maxlen=max_history)
        self._last: tuple[float, float, float] | None = None

    def observe(self, *, temp: float, valve: float, outdoor: float, dt: float) -> None:
        """Record the latest transition and re-identify parameters."""
        if self._last is not None and dt > 0:
            last_temp, last_valve, last_outdoor = self._last
            self.history.append(
                Sample(
                    dt=dt,
                    temp=last_temp,
                    next_temp=temp,
                    valve=last_valve,
                    outdoor=last_outdoor,
                )
            )
            if len(self.history) >= MIN_SAMPLES:
                self.params = identify_parameters(list(self.history), self.params)
        self._last = (temp, valve, outdoor)

    def compute_valve_pct(
        self,
        *,
        temp: float,
        target: float,
        outdoor: float | Sequence[float],
        dt: float,
        horizon: int = DEFAULT_HORIZON,
        max_opening_pct: float = 100.0,
    ) -> float:
        """Return the optimal valve opening as a percentage in [0, max].

        ``outdoor`` may be a constant or a per-step forecast series (for
        forecast-based preconditioning over a longer ``horizon``).
        """
        valve = optimize_valve(
            temp,
            target,
            outdoor,
            self.params,
            dt=dt,
            horizon=horizon,
            max_opening=max_opening_pct / 100.0,
        )
        return round(valve * 100.0, 1)

    def fit_rmse(self) -> float | None:
        """Root-mean-square residual (K/step) of the current fit over history.

        How well the learned ``(gain, loss)`` reproduces the observed
        temperature changes; lower is a better-trusted model. ``None`` until
        there are enough samples to have fitted at all.
        """
        if len(self.history) < MIN_SAMPLES:
            return None
        total = 0.0
        for s in self.history:
            predicted = s.dt * (
                self.params.gain * s.valve - self.params.loss * (s.temp - s.outdoor)
            )
            total += (predicted - (s.next_temp - s.temp)) ** 2
        return math.sqrt(total / len(self.history))

    def to_dict(self) -> dict[str, Any]:
        """Serialise learned parameters and history for persistence."""
        return {
            "gain": self.params.gain,
            "loss": self.params.loss,
            "history": [asdict(sample) for sample in self.history],
        }

    @classmethod
    def from_dict(
        cls, data: dict[str, Any], *, max_history: int = DEFAULT_MAX_HISTORY
    ) -> MpcController:
        """Restore a controller from :meth:`to_dict` output."""
        controller = cls(
            ThermalParams(gain=data["gain"], loss=data["loss"]),
            max_history=max_history,
        )
        for sample in data.get("history", []):
            controller.history.append(Sample(**sample))
        return controller


def preconditioned_valve_pct(
    controller: MpcController,
    *,
    temp: float,
    target: float,
    outdoor: float,
    series: Sequence[float] | None,
    dt: float,
) -> float:
    """Valve % for now, raised (never lowered) by the forecast look-ahead.

    The plain optimisation answers "how open right now"; when a forecast
    ``series`` is available, a second optimisation over the look-ahead may ask
    for more heat ahead of a cold spell. Taking the max guarantees
    preconditioning can only *pre-heat* — the present is never under-heated
    just because the future looks warm.
    """
    pct = controller.compute_valve_pct(temp=temp, target=target, outdoor=outdoor, dt=dt)
    if not series:
        return pct
    return max(
        pct,
        controller.compute_valve_pct(
            temp=temp, target=target, outdoor=series, dt=dt, horizon=len(series)
        ),
    )
