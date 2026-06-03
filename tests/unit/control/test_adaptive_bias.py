"""Tests for the pure adaptive AC-bias integral controller."""

from __future__ import annotations

import pytest

from custom_components.climate_orchestrator.control.adaptive_bias import (
    effective_bias,
    update_bias_integral,
)


def test_no_headroom_returns_zero() -> None:
    """With no room above the base bias, the accumulator stays at zero."""
    assert (
        update_bias_integral(
            0.0, error=2.0, dt_min=5.0, ki=0.05, max_add=0.0, cooling=True
        )
        == 0.0
    )


def test_integrates_while_cooling_above_target() -> None:
    """A warm room while cooling grows the accumulator by ki*error*dt."""
    result = update_bias_integral(
        0.0, error=2.0, dt_min=5.0, ki=0.05, max_add=2.0, cooling=True
    )
    assert result == pytest.approx(0.5)


def test_clamped_to_max_add() -> None:
    """Anti-windup caps the accumulator at the available headroom."""
    result = update_bias_integral(
        1.9, error=5.0, dt_min=10.0, ki=0.05, max_add=2.0, cooling=True
    )
    assert result == 2.0


def test_anti_windup_floor_at_zero() -> None:
    """Negative error (room below target) can't drive the add-on below zero."""
    result = update_bias_integral(
        0.1, error=-3.0, dt_min=5.0, ki=0.05, max_add=2.0, cooling=True
    )
    assert result == 0.0


def test_decays_when_not_cooling() -> None:
    """When not actively cooling, the accumulator fades toward zero."""
    result = update_bias_integral(
        1.0, error=2.0, dt_min=5.0, ki=0.05, max_add=2.0, cooling=False, decay=0.5
    )
    assert result == pytest.approx(0.5)


def test_effective_bias_adds_and_caps() -> None:
    """Effective bias is base + add-on, never below base or above the ceiling."""
    assert effective_bias(1.5, 1.0, 4.0) == pytest.approx(2.5)
    assert effective_bias(1.5, 5.0, 4.0) == pytest.approx(4.0)  # capped
    assert effective_bias(1.5, -1.0, 4.0) == pytest.approx(1.5)  # add-on floored


# --- mutation-hardening: boundary/exact-value pins (mutmut survivors) ---


def test_bias_decay_default_is_half() -> None:
    assert (
        update_bias_integral(
            1.0, error=0.0, dt_min=1.0, ki=0.1, max_add=2.0, cooling=False
        )
        == 0.5
    )


def test_bias_small_ceiling_still_accumulates() -> None:
    assert (
        update_bias_integral(
            0.4, error=1.0, dt_min=1.0, ki=0.1, max_add=0.5, cooling=True
        )
        == 0.5
    )


def test_bias_accumulates_onto_existing_integral() -> None:
    assert (
        update_bias_integral(
            1.0, error=1.0, dt_min=1.0, ki=0.1, max_add=2.0, cooling=True
        )
        == 1.1
    )


def test_bias_decay_multiplies_the_integral() -> None:
    """Decay scales the existing integral (0.8 -> 0.4), not a fixed reset."""
    assert (
        update_bias_integral(
            0.8, error=0.0, dt_min=1.0, ki=0.1, max_add=2.0, cooling=False
        )
        == 0.4
    )
