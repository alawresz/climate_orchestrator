"""Pure unit tests for the shared numeric helpers."""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st
import pytest

from custom_components.climate_orchestrator.control.numeric import clamp


@pytest.mark.parametrize(
    ("value", "lo", "hi", "expected"),
    [
        (5.0, 0.0, 10.0, 5.0),  # inside: passes through untouched
        (-1.5, 0.0, 10.0, 0.0),  # below: floored at lo
        (11.0, 0.0, 10.0, 10.0),  # above: ceiled at hi
        (0.0, 0.0, 10.0, 0.0),  # bounds are inclusive
        (10.0, 0.0, 10.0, 10.0),
        (3.0, 2.0, 2.0, 2.0),  # degenerate interval collapses to it
        (-4.0, -10.0, -2.0, -4.0),  # negative intervals work the same
    ],
)
def test_clamp(value: float, lo: float, hi: float, expected: float) -> None:
    assert clamp(value, lo, hi) == expected


@given(
    value=st.floats(allow_nan=False, allow_infinity=False),
    lo=st.floats(allow_nan=False, allow_infinity=False, max_value=1e9),
    width=st.floats(min_value=0.0, max_value=1e9, allow_nan=False),
)
def test_clamp_always_lands_in_interval(value: float, lo: float, width: float) -> None:
    hi = lo + width
    assert lo <= clamp(value, lo, hi) <= hi
