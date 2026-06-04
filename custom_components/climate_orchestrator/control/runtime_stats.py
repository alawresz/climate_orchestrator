"""Pure runtime/cycle statistics over (monotonic, running?) samples.

The coordinator keeps a rolling deque of :class:`~..models.RuntimeSample` per
device; these functions integrate it into the runtime-fraction and
cycles-per-hour diagnostics. Pure (and mutation-tested) — no Home Assistant
dependencies.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .numeric import clamp

if TYPE_CHECKING:
    from collections.abc import Sequence

    from ..models import RuntimeSample


def runtime_fraction(
    samples: Sequence[RuntimeSample], now: float, window_seconds: float
) -> float | None:
    """Fraction of the trailing window the device was running (0..1).

    Each sample holds from its timestamp until the next one (the last holds
    until ``now``); the first sample may pre-date the window so the integral
    spans the window edge.
    """
    if not samples:
        return None
    start = max(samples[0].at, now - window_seconds)
    span = now - start
    if span <= 0.0:
        return None
    running_time = 0.0
    for i, sample in enumerate(samples):
        seg_start = max(sample.at, start)
        seg_end = samples[i + 1].at if i + 1 < len(samples) else now
        if sample.running and seg_end > seg_start:
            running_time += seg_end - seg_start
    return clamp(running_time / span, 0.0, 1.0)


def cycles_per_hour(
    samples: Sequence[RuntimeSample], now: float, window_seconds: float
) -> float | None:
    """Off->on starts per hour over the trailing window (short-cycling gauge)."""
    if len(samples) < 2:
        return None
    start = max(samples[0].at, now - window_seconds)
    span = now - start
    if span <= 0.0:
        return None
    transitions = 0
    prev: bool | None = None
    for sample in samples:
        if prev is not None and not prev and sample.running and sample.at >= start:
            transitions += 1
        prev = sample.running
    return transitions * 3600.0 / span
