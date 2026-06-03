"""Tests for the pure temperature-slope estimator."""

from __future__ import annotations

import pytest

from custom_components.climate_orchestrator.control.slope import (
    temperature_slope_per_min,
)


def test_too_few_samples_returns_none() -> None:
    assert temperature_slope_per_min([]) is None
    assert temperature_slope_per_min([(0.0, 20.0)]) is None


def test_no_time_spread_returns_none() -> None:
    assert temperature_slope_per_min([(5.0, 20.0), (5.0, 21.0)]) is None


def test_rising_slope_in_kelvin_per_minute() -> None:
    # +1 K over 60 s -> +1 K/min.
    assert temperature_slope_per_min([(0.0, 20.0), (60.0, 21.0)]) == pytest.approx(1.0)
    # Linear ramp over three points keeps the same slope.
    samples = [(0.0, 20.0), (60.0, 21.0), (120.0, 22.0)]
    assert temperature_slope_per_min(samples) == pytest.approx(1.0)


def test_falling_slope_is_negative() -> None:
    assert temperature_slope_per_min([(0.0, 22.0), (60.0, 21.0)]) == pytest.approx(-1.0)


def test_regression_smooths_jitter() -> None:
    # Noisy but overall rising ~0.5 K/min; regression returns a stable positive.
    samples = [(0.0, 20.0), (60.0, 20.7), (120.0, 20.9), (180.0, 21.6)]
    slope = temperature_slope_per_min(samples)
    assert slope is not None
    assert 0.3 < slope < 0.7
