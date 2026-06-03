"""Pure unit tests for the aggregation helpers (no Home Assistant needed)."""

from __future__ import annotations

import pytest

from custom_components.climate_orchestrator.sensing.aggregate import mean_or_none


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ([20.0, 22.0], 21.0),
        ([21.0], 21.0),
        ([20.0, None, 22.0], 21.0),  # offline sensor dropped
        ([None, None], None),  # nothing usable
        ([], None),
    ],
)
def test_mean_or_none(values: list[float | None], expected: float | None) -> None:
    """The mean ignores ``None`` values and is ``None`` when nothing remains."""
    assert mean_or_none(values) == expected
