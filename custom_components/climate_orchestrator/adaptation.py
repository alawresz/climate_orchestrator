"""Weather adaptation: outdoor running mean, adaptive band, forecast cache.

``WeatherAdaptation`` owns the slow outdoor-weather state the control cycle
consumes: the exponentially-smoothed running-mean outdoor temperature (rmot)
driving the adaptive cooling-comfort shift, the would-be shifted band for the
preview sensors, and the cached hourly forecast feeding MPC preconditioning.
The pure math stays in ``control.adaptive_comfort`` and ``control.forecast``;
this module is the stateful, HA-side bookkeeping around it.
"""

from __future__ import annotations

import logging
import math
import time
from typing import TYPE_CHECKING

from homeassistant.core import callback

from .const import (
    PRECONDITION_FORECAST_REFRESH_SECONDS,
    PRECONDITION_MAX_STEPS,
    RMOT_TAU_SECONDS,
)
from .control.adaptive_comfort import adaptive_band, running_mean_update
from .control.forecast import expand_forecast
from .models import Band

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .settings import RuntimeSettings

_LOGGER = logging.getLogger(__name__)

# Cap on cached hourly forecast entries. The longest look-ahead is 8 h; two
# days is already generous — a buggy weather entity must not grow the cache.
_FORECAST_MAX_HOURS = 48
# A forecast this stale is worse than none: the optimiser would precondition
# against weather from hours ago. Refreshes retry every cycle once due, so
# 3 h means a *persistently* failing weather entity, not a blip.
_FORECAST_MAX_AGE_SECONDS = 3.0 * 3600.0


class WeatherAdaptation:
    """Running-mean outdoor state, adaptive band, and the forecast cache."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Bind to hass (forecast fetches go through the weather service)."""
        self._hass = hass
        self._rmot: float | None = None
        self._adaptive_band: Band | None = None
        self._forecast_hourly: list[float] = []
        self._forecast_fetched_at = 0.0
        # Monotonic time the forecast fetch started failing (None = healthy).
        self._fetch_failing_since: float | None = None

    @property
    def rmot(self) -> float | None:
        """Running-mean outdoor temperature (°C); None until first sample."""
        return self._rmot

    @rmot.setter
    def rmot(self, value: float | None) -> None:
        """Seed the running mean (persistence restore)."""
        self._rmot = value

    @property
    def adaptive_band_high(self) -> float | None:
        """Would-be cool edge after the adaptive-comfort shift (preview).

        Only the cool edge is ever relaxed; the heat edge is never touched,
        so there is no matching "low" accessor.
        """
        return self._adaptive_band.cool_edge if self._adaptive_band else None

    @callback
    def apply(
        self,
        base_band: Band,
        outdoor: float | None,
        settings: RuntimeSettings,
        dt_min: float,
    ) -> Band:
        """Update the running-mean outdoor temp and return the band to control on.

        Adaptive comfort only relaxes *cooling* in the heat: once the
        running-mean outdoor temperature climbs past the cool edge (plus the
        onset bias), the cool setpoint drifts up by a smooth, saturating
        amount capped at ``max_shift``. The heat edge is never touched, so a
        device is never made to work harder than the user's preset. The
        shifted band is always computed for the preview sensors; it's only
        *applied* when the toggle is on.
        """
        self._rmot = running_mean_update(
            self._rmot, outdoor, dt_seconds=dt_min * 60.0, tau_seconds=RMOT_TAU_SECONDS
        )
        heat_edge, cool_edge = adaptive_band(
            base_band.heat_edge,
            base_band.cool_edge,
            self._rmot,
            settings.adaptive_cooling_comfort_max_shift,
            bias=settings.adaptive_cooling_comfort_onset_bias,
            response=settings.adaptive_cooling_comfort_response,
        )
        self._adaptive_band = Band(heat_edge=heat_edge, cool_edge=cool_edge)
        return self._adaptive_band if settings.adaptive_cooling_comfort else base_band

    async def refresh_forecast(
        self, settings: RuntimeSettings, weather_entity: str | None
    ) -> None:
        """Fetch and cache the weather entity's hourly outdoor forecast.

        Only when preconditioning is enabled and a weather entity is
        configured; rate-limited to ``PRECONDITION_FORECAST_REFRESH_SECONDS``.
        Failures are swallowed (the feature simply no-ops without a forecast),
        but a *persistent* failure is tracked so a repair can surface it — see
        :meth:`is_forecast_failing`.
        """
        if not settings.forecast_preconditioning or weather_entity is None:
            self._forecast_hourly = []
            self._fetch_failing_since = None
            return
        now = time.monotonic()
        if (
            self._forecast_hourly
            and now - self._forecast_fetched_at < PRECONDITION_FORECAST_REFRESH_SECONDS
        ):
            return
        temps = await self._fetch_hourly(weather_entity)
        if temps:
            self._forecast_hourly = temps[:_FORECAST_MAX_HOURS]
            self._forecast_fetched_at = now
            self._fetch_failing_since = None
        elif self._fetch_failing_since is None:
            # First failed/empty fetch since the last success: start the clock.
            self._fetch_failing_since = now

    async def _fetch_hourly(self, weather_entity: str) -> list[float] | None:
        """Pull the hourly outdoor-temperature series, or ``None`` if unusable.

        ``None`` covers both a raising service and a malformed/empty response —
        both mean "no usable forecast" to the cache and the failure tracker.
        """
        try:
            response = await self._hass.services.async_call(
                "weather",
                "get_forecasts",
                {"entity_id": weather_entity, "type": "hourly"},
                blocking=True,
                return_response=True,
            )
        except Exception:
            _LOGGER.debug("climate_orchestrator: forecast fetch failed", exc_info=True)
            return None
        # The service response is loosely typed JSON; narrow every step.
        if not isinstance(response, dict):
            return None
        device_block = response.get(weather_entity)
        if not isinstance(device_block, dict):
            return None
        entries = device_block.get("forecast")
        if not isinstance(entries, list):
            return None
        temps: list[float] = []
        for entry in entries:
            if isinstance(entry, dict):
                temp = entry.get("temperature")
                if (
                    isinstance(temp, int | float)
                    and not isinstance(temp, bool)
                    and math.isfinite(temp)
                ):
                    temps.append(float(temp))
        return temps or None

    def is_forecast_failing(self, *, threshold: float) -> bool:
        """Whether forecast fetches have failed continuously for ``threshold`` s.

        Only ever true while preconditioning is enabled with a weather entity
        configured — the disabled/no-entity path clears the failure clock — so
        callers needn't re-check those conditions.
        """
        since = self._fetch_failing_since
        return since is not None and time.monotonic() - since >= threshold

    @callback
    def precondition_series(
        self, dt_min: float, settings: RuntimeSettings
    ) -> list[float] | None:
        """Per-step outdoor forecast series for the valve optimiser, or ``None``.

        Interpolates the cached hourly forecast onto the control step over the
        preconditioning look-ahead; ``None`` when the feature is off or there
        is no forecast yet.
        """
        if not settings.forecast_preconditioning or not self._forecast_hourly:
            return None
        if time.monotonic() - self._forecast_fetched_at > _FORECAST_MAX_AGE_SECONDS:
            # The weather entity has been failing for hours; preconditioning
            # against its last words would steer the valve on dead data.
            return None
        steps = round(settings.preconditioning_horizon * 60.0 / dt_min)
        steps = max(1, min(steps, PRECONDITION_MAX_STEPS))
        series = expand_forecast(self._forecast_hourly, dt_min, steps)
        return series or None
