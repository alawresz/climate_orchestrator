"""Tests for the pure adaptive-comfort module."""

from __future__ import annotations

import math

import pytest

from custom_components.climate_orchestrator.control.adaptive_comfort import (
    adaptive_band,
    cool_edge_shift,
    running_mean_update,
)


def test_running_mean_seeds_then_blends() -> None:
    """First sample seeds; later samples blend toward the new value."""
    assert running_mean_update(None, 20.0, dt_seconds=60, tau_seconds=3600) == 20.0
    blended = running_mean_update(20.0, 30.0, dt_seconds=3600, tau_seconds=3600)
    assert 20.0 < blended < 30.0
    # A missing sample leaves the mean untouched.
    assert running_mean_update(21.0, None, dt_seconds=60, tau_seconds=3600) == 21.0


def test_cool_edge_shift_is_zero_below_onset() -> None:
    """No excess (or no cap / no response) means no shift."""
    assert cool_edge_shift(0.0, 2.0, 5.0) == 0.0
    assert cool_edge_shift(-3.0, 2.0, 5.0) == 0.0
    assert cool_edge_shift(5.0, 0.0, 5.0) == 0.0
    assert cool_edge_shift(5.0, 2.0, 0.0) == 0.0


def test_cool_edge_shift_saturates_toward_cap() -> None:
    """Rises smoothly with excess and asymptotically approaches max_shift."""
    # At excess == response, ~63% of the cap.
    assert cool_edge_shift(5.0, 2.0, 5.0) == pytest.approx(2.0 * (1.0 - math.exp(-1.0)))
    # Monotone increasing, never exceeds the cap.
    prev = 0.0
    for excess in (1.0, 3.0, 6.0, 12.0, 30.0):
        s = cool_edge_shift(excess, 2.0, 5.0)
        assert prev < s < 2.0
        prev = s


def test_mild_outdoor_leaves_band_unchanged() -> None:
    """Below the onset (cool_edge + bias) nothing shifts; heat never moves."""
    # cool 24.5, bias +1 -> onset 25.5; outdoor 22 is well below.
    assert adaptive_band(20.5, 24.5, 22.0, 2.0, bias=1.0, response=5.0) == (
        20.5,
        24.5,
    )


def test_warm_outdoor_relaxes_only_cool_edge() -> None:
    """Above the onset the cool edge eases up by the saturating amount."""
    # onset 25.5, outdoor 28 -> excess 2.5, response 5.
    heat, cool = adaptive_band(20.5, 24.5, 28.0, 2.0, bias=1.0, response=5.0)
    assert heat == 20.5
    assert cool == pytest.approx(24.5 + 2.0 * (1.0 - math.exp(-2.5 / 5.0)))


def test_negative_bias_starts_earlier() -> None:
    """A negative bias lowers the onset so relaxation begins at cooler outdoor."""
    # cool 24.5, bias -1 -> onset 23.5; outdoor 24 -> excess 0.5.
    heat, cool = adaptive_band(20.5, 24.5, 24.0, 2.0, bias=-1.0, response=5.0)
    assert heat == 20.5
    assert cool == pytest.approx(24.5 + 2.0 * (1.0 - math.exp(-0.5 / 5.0)))


def test_extreme_heat_saturates_at_cap_not_cliffs() -> None:
    """Very hot outdoor approaches, but never exceeds, the +max_shift cap."""
    heat, cool = adaptive_band(20.5, 24.5, 45.0, 2.0, bias=1.0, response=5.0)
    assert heat == 20.5
    assert 26.0 < cool < 26.5  # asymptotic, just under the cap


def test_no_running_mean_leaves_band_unchanged() -> None:
    assert adaptive_band(20.5, 24.5, None, 2.0, bias=1.0, response=5.0) == (
        20.5,
        24.5,
    )


# --- mutation-hardening: boundary/exact-value pins (mutmut survivors) ---


def test_running_mean_guards_and_blend() -> None:
    # tau == 0 / dt == 0 -> reseed with the sample, exactly.
    assert running_mean_update(10.0, 20.0, dt_seconds=60.0, tau_seconds=0.0) == 20.0
    assert running_mean_update(10.0, 20.0, dt_seconds=0.0, tau_seconds=600.0) == 20.0
    # Small-but-positive tau and dt still blend (not reseed).
    assert running_mean_update(
        10.0, 20.0, dt_seconds=0.1, tau_seconds=0.5
    ) == pytest.approx(11.8127, abs=1e-3)
    assert running_mean_update(
        10.0, 20.0, dt_seconds=0.5, tau_seconds=600.0
    ) == pytest.approx(10.008330, abs=1e-5)
    # Exact blend value pins the alpha * (sample - previous) form.
    assert running_mean_update(
        10.0, 20.0, dt_seconds=60.0, tau_seconds=600.0
    ) == pytest.approx(10.9516258, abs=1e-6)


def test_cool_edge_shift_small_caps_and_response() -> None:
    """Caps/response in (0, 1] are honoured, not treated as disabled."""
    assert cool_edge_shift(1.0, 0.5, 5.0) == pytest.approx(0.0906346, abs=1e-6)
    assert cool_edge_shift(1.0, 2.0, 0.5) == pytest.approx(1.7293294, abs=1e-6)
