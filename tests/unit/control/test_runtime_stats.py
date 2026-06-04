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
