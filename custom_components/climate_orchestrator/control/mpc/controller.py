"""The MPC controller: learn the room, then optimise the valve.

Each cycle the controller observes the latest transition (feeding online system
identification) and computes the valve opening for the next interval. Its
learned state is serialisable so it survives restarts (docs/internals/mpc.md
and docs/internals/persistence.md). Pure.
"""

from __future__ import annotations

from collections import deque
from dataclasses import asdict
import logging
import math
from typing import TYPE_CHECKING, Any

from ...const import MPC_MIN_SAMPLES as MIN_SAMPLES
from ..numeric import clamp
from .model import (
    DEFAULT_PARAMS,
    MAX_GAIN,
    MAX_LOSS,
    Sample,
    ThermalParams,
    identify_parameters,
)
from .observer import MAX_VARIANCE, MEASUREMENT_VAR, KalmanState, predict, update
from .optimizer import DEFAULT_HORIZON, optimize_valve

if TYPE_CHECKING:
    from collections.abc import Sequence

_LOGGER = logging.getLogger(__name__)

DEFAULT_MAX_HISTORY = 200
# Transitions longer than this (HA freeze, restart gap, long device outage)
# carry essentially no information about the valve's effect — the room has
# re-equilibrated several times over — and a huge dt skews the fit and blows
# up the Kalman projection. Such gaps re-anchor instead of being learned from.
MAX_SAMPLE_DT_MIN = 30.0
# Below this RMS of observed per-step temperature change (K), the room is
# barely moving (noise-dominated) and fit quality can't be judged — relative
# error is reported as unknown rather than spuriously high.
_MIN_FIT_SIGNAL = 0.05


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
        self.kalman: KalmanState | None = None

    def observe(self, *, temp: float, valve: float, outdoor: float, dt: float) -> None:
        """Record the latest transition, re-identify, and refresh the estimate.

        System identification deliberately consumes *raw* transitions — fitting
        the model to its own Kalman-smoothed output would be circular. The
        filter only shapes what the optimiser plans from
        (:attr:`estimated_temperature`).

        Non-finite inputs are ignored outright; a gap longer than
        ``MAX_SAMPLE_DT_MIN`` re-anchors the estimate on the new measurement
        instead of being learned from.
        """
        if not all(math.isfinite(v) for v in (temp, valve, outdoor, dt)):
            return
        bridgeable = self._last is not None and 0 < dt <= MAX_SAMPLE_DT_MIN
        if bridgeable:
            last_temp, last_valve, last_outdoor = self._last  # type: ignore[misc]
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
        # Kalman: project the previous estimate across the transition that just
        # elapsed (the *previous* valve/outdoor held for dt), then correct with
        # the new measurement. The first measurement — or the first after an
        # unbridgeable gap — (re-)anchors the state; dt <= 0 (same-instant
        # re-read) corrects without projecting.
        if self.kalman is None or dt > MAX_SAMPLE_DT_MIN:
            self.kalman = KalmanState(temp=temp, variance=MEASUREMENT_VAR)
        else:
            if bridgeable:
                _, last_valve, last_outdoor = self._last  # type: ignore[misc]
                self.kalman = predict(
                    self.kalman, last_valve, last_outdoor, self.params, dt
                )
            self.kalman = update(self.kalman, temp)
        self._last = (temp, valve, outdoor)

    @property
    def estimated_temperature(self) -> float | None:
        """Kalman-filtered room temperature (``None`` before any observation)."""
        return self.kalman.temp if self.kalman is not None else None

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
        # Final hardware clamp: whatever the caller passed as max, a valve
        # opening outside [0, 100] is never a valid command.
        return round(clamp(valve * 100.0, 0.0, 100.0), 1)

    @staticmethod
    def _residual(sample: Sample, params: ThermalParams) -> float:
        """Per-step model residual (K): predicted change minus observed change.

        The one place the discretised model is evaluated for scoring, so the
        formula can't drift between ``fit_rmse`` and its callers. Takes
        ``params`` explicitly so a whole scoring pass uses one consistent
        ``(gain, loss)`` even if the fit is re-identified mid-read.
        """
        predicted = sample.dt * (
            params.gain * sample.valve - params.loss * (sample.temp - sample.outdoor)
        )
        return predicted - (sample.next_temp - sample.temp)

    def _rmse_over(self, history: Sequence[Sample]) -> float:
        """RMS residual over a fixed sample list under the current params."""
        params = self.params  # pin once: an atomic read of the frozen pair
        residuals = [self._residual(s, params) for s in history]
        return math.sqrt(sum(r * r for r in residuals) / len(residuals))

    def fit_rmse(self) -> float | None:
        """Root-mean-square residual (K/step) of the current fit over history.

        How well the learned ``(gain, loss)`` reproduces the observed
        temperature changes; lower is a better-trusted model. ``None`` until
        there are enough samples to have fitted at all.
        """
        # Snapshot the deque: the MPC math runs in an executor thread and may be
        # appending while a loop-side diagnostic read iterates here. Copying
        # first avoids "deque mutated during iteration"; ``list(deque)`` is
        # atomic under the GIL.
        history = list(self.history)
        if len(history) < MIN_SAMPLES:
            return None
        return self._rmse_over(history)

    def relative_fit_error(self) -> float | None:
        """Fit residual as a fraction of the room's actual movement, or ``None``.

        ``fit_rmse`` is an absolute figure whose scale depends on ``dt`` and how
        much the room moves, so it can't carry a fixed "this fit is bad"
        threshold. This normalises it by the RMS of the observed per-step
        changes: ``0`` is a perfect fit, ``~1`` means the model explains no more
        than predicting "no change," ``>1`` is worse than nothing. ``None``
        until there are enough samples, or when the room is too static to judge
        (see ``_MIN_FIT_SIGNAL``) — a model that can't be evaluated isn't bad.

        A persistently high value is the tell that the model is mis-specified
        for the hardware — e.g. a weather-compensated radiator whose output
        varies with the supply temperature the constant ``gain`` can't capture.
        """
        history = list(self.history)  # one snapshot for both ratio terms (see fit_rmse)
        if len(history) < MIN_SAMPLES:
            return None
        observed = [s.next_temp - s.temp for s in history]
        rms_observed = math.sqrt(sum(o * o for o in observed) / len(observed))
        if rms_observed < _MIN_FIT_SIGNAL:
            return None
        return self._rmse_over(history) / rms_observed

    def to_dict(self) -> dict[str, Any]:
        """Serialise learned parameters and history for persistence."""
        payload: dict[str, Any] = {
            "gain": self.params.gain,
            "loss": self.params.loss,
            "history": [asdict(sample) for sample in self.history],
        }
        if self.kalman is not None:
            payload["kalman"] = asdict(self.kalman)
        return payload

    @classmethod
    def from_dict(
        cls, data: dict[str, Any], *, max_history: int = DEFAULT_MAX_HISTORY
    ) -> MpcController:
        """Restore a controller from :meth:`to_dict` output.

        Raises ``TypeError``/``KeyError`` on malformed
        payloads; the coordinator catches these per entry on restore.
        """
        gain, loss = data.get("gain"), data.get("loss")
        if (
            not isinstance(gain, int | float)
            or not isinstance(loss, int | float)
            or not math.isfinite(gain)
            or not math.isfinite(loss)
        ):
            # Python's json round-trips NaN/Infinity, so a corrupted store can
            # hand back "numbers" that would poison every prediction.
            raise TypeError
        controller = cls(
            # Re-clamp to the fit bounds: a store written by an older release
            # (or by hand) must not seed parameters the fitter itself refuses.
            ThermalParams(
                gain=clamp(float(gain), 0.0, MAX_GAIN),
                loss=clamp(float(loss), 0.0, MAX_LOSS),
            ),
            max_history=max_history,
        )
        dropped = 0
        for sample in data.get("history", []):
            restored = Sample(**sample)
            if all(
                isinstance(v, int | float) and math.isfinite(v)
                for v in (
                    restored.dt,
                    restored.temp,
                    restored.next_temp,
                    restored.valve,
                    restored.outdoor,
                )
            ):
                controller.history.append(restored)
            else:
                dropped += 1
        if dropped:
            # to_dict only ever writes finite samples, so any drop means the
            # store was corrupted — say so instead of silently re-learning.
            _LOGGER.warning(
                "Discarded %d corrupt MPC history sample(s) on restore;"
                " the model continues from the remaining %d",
                dropped,
                len(controller.history),
            )
        if (kalman := data.get("kalman")) is not None:
            state = KalmanState(**kalman)
            if (
                isinstance(state.temp, int | float)
                and isinstance(state.variance, int | float)
                and math.isfinite(state.temp)
                and math.isfinite(state.variance)
                and state.variance >= 0.0
            ):
                controller.kalman = KalmanState(
                    temp=float(state.temp),
                    variance=min(float(state.variance), MAX_VARIANCE),
                )
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
