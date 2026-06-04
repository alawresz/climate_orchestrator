"""Pure unit tests for the defensive state-reading helpers."""

from __future__ import annotations

import pytest

from custom_components.climate_orchestrator.util import as_float


def test_parses_numbers_and_numeric_strings():
    assert as_float(21.5) == 21.5
    assert as_float("21.5") == 21.5
    assert as_float(7) == 7.0
    assert as_float("-3") == -3.0


def test_rejects_garbage():
    assert as_float(None) is None
    assert as_float("warm") is None
    assert as_float("") is None
    assert as_float(object()) is None


@pytest.mark.parametrize(
    "value",
    ["nan", "NaN", "inf", "-inf", "Infinity", float("nan"), float("inf")],
)
def test_rejects_non_finite_values(value):
    """float('nan') parses without raising — it must still be rejected."""
    assert as_float(value) is None
