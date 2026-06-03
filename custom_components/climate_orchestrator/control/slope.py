"""Temperature slope (pure).

Estimates the rate of change of a temperature signal in kelvin per minute via
ordinary least-squares over a short trailing window of ``(time, temperature)``
samples. A regression (rather than an endpoint difference) keeps the figure
stable against sensor jitter. The coordinator owns the sample buffer; this keeps
the maths trivially testable.
"""

from __future__ import annotations

from collections.abc import Sequence


def temperature_slope_per_min(samples: Sequence[tuple[float, float]]) -> float | None:
    """K/min slope of ``(time_seconds, temperature)`` samples, or ``None``.

    Returns ``None`` when there are fewer than two samples or no time spread
    (so the slope is undefined).
    """
    count = len(samples)
    if count < 2:
        return None

    times = [t for t, _ in samples]
    temps = [c for _, c in samples]
    time_mean = sum(times) / count
    temp_mean = sum(temps) / count

    var_t = sum((t - time_mean) ** 2 for t in times)
    if var_t <= 0.0:
        return None

    cov_tc = sum(
        (t - time_mean) * (c - temp_mean) for t, c in zip(times, temps, strict=False)
    )
    return (cov_tc / var_t) * 60.0
