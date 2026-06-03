"""Pure aggregation helpers — no Home Assistant dependencies.

Kept import-free of `homeassistant` so the numeric core can be unit-tested on
any Python without the full HA stack.
"""

from __future__ import annotations

from collections.abc import Iterable


def mean_or_none(values: Iterable[float | None]) -> float | None:
    """Return the mean of the non-``None`` values, or ``None`` if there are none.

    Offline/unknown sensors are represented as ``None`` and dropped from the
    mean rather than poisoning it (see DESIGN.md §6.4).
    """
    present = [value for value in values if value is not None]
    if not present:
        return None
    return sum(present) / len(present)
