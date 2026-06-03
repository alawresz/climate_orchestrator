"""Setpoint write throttling (pure).

The AC's proportional compressor anchor nudges the commanded setpoint nearly
every cycle as the unit's own reading and the room delta drift. Re-issuing it
each time spams the device's radio for no comfort gain, so we hold the last
written value unless the change is meaningful *and* enough time has passed —
with a periodic keep-alive so a stale value can't linger forever.
"""

from __future__ import annotations


def throttle_setpoint(
    prev: float | None,
    prev_ts: float | None,
    new: float,
    now: float,
    *,
    min_change: float,
    min_interval_s: float,
    keepalive_s: float,
) -> tuple[float, float]:
    """Return the ``(value_to_send, timestamp)`` for a setpoint write.

    Holds ``prev`` (returning the previous value + timestamp, so a downstream
    diff becomes a no-op) unless:

    * there is no previous value (first write), or
    * ``keepalive_s`` has elapsed (periodic re-assert), or
    * the change is at least ``min_change`` *and* at least ``min_interval_s``
      has elapsed since the last write.
    """
    if prev is None or prev_ts is None:
        return new, now
    elapsed = now - prev_ts
    if elapsed >= keepalive_s:
        return new, now
    if abs(new - prev) >= min_change and elapsed >= min_interval_s:
        return new, now
    return prev, prev_ts
