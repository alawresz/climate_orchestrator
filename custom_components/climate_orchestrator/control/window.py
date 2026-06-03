"""Window-open debounce (pure).

A window opening should not necessarily stop heating/cooling immediately: a
brief airing shouldn't kill a long heat-up. This module holds the pure decision
of *whether an open window should currently suppress a device*, given when the
window first opened, the current time, and a configured grace delay. The
coordinator owns the timing state (when each area's window opened); this keeps
the rule itself trivially testable.
"""

from __future__ import annotations


def window_suppresses(
    raw_open: bool,
    opened_at: float | None,
    now: float,
    delay_seconds: float,
) -> bool:
    """Whether an open window should suppress heating/cooling right now.

    ``raw_open`` is the live sensor state, ``opened_at`` the timestamp (same
    clock as ``now``) at which the window most recently became open, and
    ``delay_seconds`` the configured grace period. A closed window never
    suppresses; an open one suppresses only once it has stayed open for at least
    the delay. A delay of ``0`` suppresses immediately.
    """
    if not raw_open:
        return False
    if delay_seconds <= 0.0:
        return True
    if opened_at is None:
        return False
    return (now - opened_at) >= delay_seconds
