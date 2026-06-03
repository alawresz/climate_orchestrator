"""Expand an hourly outdoor forecast onto the control timestep (pure).

The MPC valve optimiser rolls the room model forward one control step at a time,
so it needs an outdoor temperature *per step*. Weather integrations give an
hourly series; this linearly interpolates that onto the optimiser's step grid and
holds the last value once the forecast runs out. No Home Assistant dependencies.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence


def expand_forecast(
    hourly: Sequence[float], step_minutes: float, steps: int
) -> list[float]:
    """Interpolate an hourly temperature series onto ``steps`` control steps.

    ``hourly[i]`` is the outdoor temperature ``i`` hours from now. Step ``k`` is
    ``k * step_minutes`` minutes ahead; its value is linearly interpolated between
    the bracketing hourly points, and held flat at ``hourly[-1]`` beyond the end
    of the forecast. Returns an empty list when there's no forecast or no steps.
    """
    if not hourly or steps <= 0 or step_minutes <= 0:
        return []
    last = len(hourly) - 1
    series: list[float] = []
    for k in range(steps):
        hours = k * step_minutes / 60.0
        i = int(hours)
        if i >= last:
            series.append(float(hourly[last]))
        else:
            frac = hours - i
            series.append(float(hourly[i] + frac * (hourly[i + 1] - hourly[i])))
    return series
