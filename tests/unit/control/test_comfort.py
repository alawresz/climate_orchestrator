"""Tests for the comfort math (apparent temperature, dew point)."""

from __future__ import annotations

import pytest

from custom_components.climate_orchestrator.control.comfort import (
    apparent_temperature,
    dew_point,
    effective_temperature,
)


def test_apparent_temperature_rises_with_humidity() -> None:
    """At a fixed temperature, more humidity feels warmer."""
    assert apparent_temperature(28.0, 80) > apparent_temperature(28.0, 30)


def test_apparent_temperature_reference_value() -> None:
    """Sanity-check against a known reference point."""
    assert apparent_temperature(25.0, 50) == pytest.approx(26.2, abs=0.3)


def test_apparent_temperature_below_drybulb_when_dry() -> None:
    """In cool, dry air apparent temperature dips just below dry-bulb."""
    assert apparent_temperature(20.0, 30) < 20.0


def test_dew_point_reference_value() -> None:
    """Dew point for 25 °C / 50% RH is ~13.9 °C."""
    assert dew_point(25.0, 50) == pytest.approx(13.9, abs=0.4)


def test_dew_point_never_exceeds_temperature() -> None:
    """Dew point cannot be above the air temperature."""
    assert dew_point(22.0, 60) <= 22.0


def test_dew_point_lower_in_drier_air() -> None:
    """Drier air has a lower dew point at the same temperature."""
    assert dew_point(22.0, 30) < dew_point(22.0, 80)


def test_effective_temperature_falls_back_to_drybulb() -> None:
    """No humidity, or comfort disabled, returns the dry-bulb temperature."""
    assert effective_temperature(21.0, None) == 21.0
    assert effective_temperature(21.0, 50, use_comfort=False) == 21.0


def test_effective_temperature_uses_apparent_when_enabled() -> None:
    """With humidity and comfort on (default influence 1.0), equals apparent."""
    assert effective_temperature(21.0, 50) == pytest.approx(
        apparent_temperature(21.0, 50)
    )


def test_influence_blends_between_drybulb_and_apparent() -> None:
    """Influence scales the humidity effect: 0 -> dry-bulb, 0.5 -> halfway."""
    dry = 28.0
    apparent = apparent_temperature(dry, 80)
    assert effective_temperature(dry, 80, influence=0.0) == dry
    assert effective_temperature(dry, 80, influence=1.0) == pytest.approx(apparent)
    assert effective_temperature(dry, 80, influence=0.5) == pytest.approx(
        dry + 0.5 * (apparent - dry)
    )
    # >1 amplifies the humidity push beyond the raw apparent temperature.
    assert effective_temperature(dry, 80, influence=2.0) > apparent


# --- mutation-hardening: boundary/exact-value pins (mutmut survivors) ---


def test_effective_temperature_defaults_are_full_comfort() -> None:
    """No-kwargs call equals use_comfort=True, influence=1.0 exactly."""
    assert effective_temperature(24.0, 90.0) == effective_temperature(
        24.0, 90.0, use_comfort=True, influence=1.0
    )
    assert effective_temperature(24.0, 90.0) == pytest.approx(28.8364, abs=1e-3)


def test_dew_point_at_very_low_humidity() -> None:
    """The log guard floor is tiny; 0.5% RH still yields a deep dew point."""
    assert dew_point(20.0, 0.5) == pytest.approx(-44.3196, abs=0.01)
