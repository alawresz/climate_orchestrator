"""Adaptive comfort - outdoor-referenced cool-edge relaxation (pure).

When it's genuinely hot *outside*, chasing the same cool setpoint you'd want on
a mild day wastes energy for little comfort gain. So once the running-mean
outdoor temperature climbs past the cool edge (plus a user bias), we let the
cool setpoint drift upward - but smoothly, and capped:

    onset      = cool_edge + bias
    excess     = max(0, outdoor - onset)
    cool_shift = max_shift * (1 - exp(-excess / response))
    adaptive_cool = cool_edge + cool_shift

The shift starts at zero at the onset and *saturates* toward ``max_shift`` as
it gets hotter (an exponential approach), so the setpoint eases up gently
instead of jumping and then flat-lining. ``response`` is the characteristic
number of degrees of excess over which ~63% of ``max_shift`` is reached; a
larger value makes the climb gentler.

The heat edge is never touched - this only relaxes cooling in the heat. The
running mean itself is an exponential running mean of the outdoor temperature.
All pure functions.
"""

from __future__ import annotations

import math


def running_mean_update(
    previous: float | None,
    sample: float | None,
    *,
    dt_seconds: float,
    tau_seconds: float,
) -> float | None:
    """Advance the exponential running-mean outdoor temperature.

    Returns the unchanged ``previous`` when there's no new sample; seeds with the
    first sample; otherwise blends by ``alpha = 1 - exp(-dt/tau)``.
    """
    if sample is None:
        return previous
    if previous is None or tau_seconds <= 0.0 or dt_seconds <= 0.0:
        return sample
    alpha = 1.0 - math.exp(-dt_seconds / tau_seconds)
    return previous + alpha * (sample - previous)


def cool_edge_shift(excess: float, max_shift: float, response: float) -> float:
    """Saturating cool-edge shift for a given outdoor *excess* over the onset.

    Zero at and below the onset; rises with an ever-decreasing slope and
    asymptotically approaches ``max_shift``. ``response`` sets the gentleness
    (degrees of excess for ~63% of the cap).
    """
    if excess <= 0.0 or max_shift <= 0.0 or response <= 0.0:
        return 0.0
    return max_shift * (1.0 - math.exp(-excess / response))


def adaptive_band(
    heat_edge: float,
    cool_edge: float,
    outdoor: float | None,
    max_shift: float,
    *,
    bias: float,
    response: float,
) -> tuple[float, float]:
    """Relax the cool edge once the outdoor temp passes ``cool_edge + bias``.

    The cool edge rises by a smooth, saturating amount that grows with how far
    the outdoor temperature exceeds the onset, capped at ``max_shift``. A
    negative ``bias`` starts the relaxation earlier (cooler outside), a positive
    one later. The heat edge is never changed. Returns the band unchanged when
    the outdoor temperature is unknown or below the onset.
    """
    if outdoor is None:
        return heat_edge, cool_edge
    excess = outdoor - (cool_edge + bias)
    return heat_edge, cool_edge + cool_edge_shift(excess, max_shift, response)
