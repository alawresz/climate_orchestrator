"""Small shared helpers for reading Home Assistant state defensively."""

from __future__ import annotations

import math

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, callback


def as_float(value: object) -> float | None:
    """Coerce a value to a *finite* ``float``, or ``None`` if it isn't one.

    ``float("nan")``/``float("inf")`` parse without raising, so a sensor
    reporting ``nan`` would otherwise slip through and silently poison every
    mean and comparison downstream. Non-finite values are rejected here, once,
    for every numeric read in the integration.
    """
    try:
        result = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


@callback
def float_state(hass: HomeAssistant, entity_id: str | None) -> float | None:
    """Read an entity's state as a float; ``None`` if absent/unknown/non-numeric.

    The one idiom for every numeric state read, so missing, unavailable,
    unknown, and garbage states all degrade the same way everywhere.
    """
    if entity_id is None:
        return None
    state = hass.states.get(entity_id)
    if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
        return None
    return as_float(state.state)
