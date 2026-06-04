"""Pure unit tests for the runtime/cycle statistics."""

from __future__ import annotations

import pytest

from custom_components.climate_orchestrator.control.runtime_stats import (
    cycles_per_hour,
    runtime_fraction,
)
from custom_components.climate_orchestrator.models import RuntimeSample

_NOW = 10_000.0
_HOUR = 3600.0


def _samples(*points: tuple[float, bool]) -> list[RuntimeSample]:
    return [
        RuntimeSample(at=_NOW + offset, running=running) for offset, running in points
    ]


def test_fraction_integrates_run_segments() -> None:
    """Off, on@-1800, off@-900, on@-600 -> (900 + 600) / 3600."""
    samples = _samples((-3600, False), (-1800, True), (-900, False), (-600, True))
    assert runtime_fraction(samples, _NOW, _HOUR) == pytest.approx(1500 / 3600)


def test_cycles_counts_off_to_on_transitions() -> None:
    samples = _samples((-3600, False), (-1800, True), (-900, False), (-600, True))
    assert cycles_per_hour(samples, _NOW, _HOUR) == pytest.approx(2.0)


def test_empty_and_single_sample_edges() -> None:
    assert runtime_fraction([], _NOW, _HOUR) is None
    assert cycles_per_hour([], _NOW, _HOUR) is None
    assert cycles_per_hour(_samples((-10, True)), _NOW, _HOUR) is None


def test_fraction_spans_only_since_first_sample() -> None:
    """A device first seen mid-window is judged over its own span, not the window."""
    assert runtime_fraction(_samples((-1800, True)), _NOW, _HOUR) == 1.0


def test_fraction_clips_samples_older_than_the_window() -> None:
    """A sample pre-dating the window holds across the edge but isn't over-counted."""
    assert runtime_fraction(_samples((-7200, True)), _NOW, _HOUR) == 1.0


def test_transitions_before_the_window_do_not_count() -> None:
    samples = _samples((-7200, False), (-7100, True))
    assert cycles_per_hour(samples, _NOW, _HOUR) == 0.0


# --- mutation-hardening: boundary/exact-value pins (mutmut survivors) --------


def test_zero_span_returns_none_not_division_error() -> None:
    """A sample exactly at `now` gives span 0 — None, never a ZeroDivisionError."""
    assert runtime_fraction(_samples((0, True)), _NOW, _HOUR) is None
    assert cycles_per_hour(_samples((0, False), (0, True)), _NOW, _HOUR) is None


def test_subsecond_spans_are_valid() -> None:
    """Spans in (0, 1] seconds compute normally (not treated as empty)."""
    assert runtime_fraction(_samples((-0.5, True)), _NOW, _HOUR) == 1.0
    assert cycles_per_hour(
        _samples((-0.5, False), (-0.25, True)), _NOW, _HOUR
    ) == pytest.approx(7200.0)


def test_running_segment_ends_at_the_next_sample() -> None:
    """on@-1800, off@-900: the run is exactly half the 1800 s span."""
    assert runtime_fraction(
        _samples((-1800, True), (-900, False)), _NOW, _HOUR
    ) == pytest.approx(0.5)


def test_a_running_first_sample_is_not_a_transition() -> None:
    """The first sample has no predecessor: no off->on edge to count."""
    assert cycles_per_hour(_samples((-1800, True), (-900, False)), _NOW, _HOUR) == 0.0


def test_transition_exactly_at_the_window_edge_counts() -> None:
    assert cycles_per_hour(
        _samples((-7200, False), (-3600, True)), _NOW, _HOUR
    ) == pytest.approx(1.0)
