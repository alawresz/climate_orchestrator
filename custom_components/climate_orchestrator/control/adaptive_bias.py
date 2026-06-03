"""Adaptive AC setpoint bias (pure).

The fixed ``ac_setpoint_bias`` is a manual guess at how far below the real
target the AC must be told to cool, because its onboard sensor satisfies before
the room (measured by the area sensor) does. This module replaces the guesswork
with **integral feedback**: while the AC is actively cooling and the room is
still above target, an accumulator grows and adds to the bias, so a room that's
cooling too slowly automatically gets a more aggressive setpoint. When the AC
isn't cooling the accumulator decays back toward zero. The result self-tunes
around the manual bias (which stays the floor) and eliminates the steady-state
offset a fixed bias can only approximate.

Standard PI-style integral action with anti-windup (the accumulator is clamped
to ``[0, max_add]``). Pure functions — the coordinator owns the per-AC state.
"""

from __future__ import annotations

from .numeric import clamp


def update_bias_integral(
    integral: float,
    *,
    error: float,
    dt_min: float,
    ki: float,
    max_add: float,
    cooling: bool,
    decay: float = 0.5,
) -> float:
    """Advance the bias accumulator one cycle and return the clamped value.

    ``error`` is ``room_temp - target`` (positive while the room is still too
    warm). While ``cooling`` the accumulator integrates ``ki * error * dt_min``;
    otherwise it decays toward zero by ``decay``. The result is clamped to
    ``[0, max_add]`` for anti-windup, so the adaptive part never drops the bias
    below the manual base and never exceeds the configured ceiling.
    """
    if max_add <= 0.0:
        return 0.0
    if cooling:
        integral += ki * error * dt_min
    else:
        integral *= decay
    return clamp(integral, 0.0, max_add)


def effective_bias(base: float, integral: float, max_total: float) -> float:
    """Combine the manual base bias and the learned add-on, capped at the max."""
    return min(base + max(0.0, integral), max_total)
