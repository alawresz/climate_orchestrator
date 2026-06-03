"""Tests for the pure window-open debounce predicate."""

from __future__ import annotations

from custom_components.climate_orchestrator.control.window import window_suppresses


def test_closed_window_never_suppresses() -> None:
    assert window_suppresses(False, opened_at=None, now=100.0, delay_seconds=300.0) is (
        False
    )
    # Even with a stale "opened_at", a closed window does not suppress.
    assert (
        window_suppresses(False, opened_at=0.0, now=100.0, delay_seconds=0.0) is False
    )


def test_zero_delay_suppresses_immediately() -> None:
    assert window_suppresses(True, opened_at=None, now=0.0, delay_seconds=0.0) is True
    assert (
        window_suppresses(True, opened_at=100.0, now=100.0, delay_seconds=0.0) is True
    )


def test_delay_holds_until_elapsed() -> None:
    # Just opened: within the grace period, do not suppress yet.
    assert window_suppresses(True, opened_at=100.0, now=100.0, delay_seconds=300.0) is (
        False
    )
    assert window_suppresses(True, opened_at=100.0, now=399.0, delay_seconds=300.0) is (
        False
    )
    # At/after the delay boundary, suppress.
    assert window_suppresses(True, opened_at=100.0, now=400.0, delay_seconds=300.0) is (
        True
    )
    assert window_suppresses(True, opened_at=100.0, now=500.0, delay_seconds=300.0) is (
        True
    )


def test_open_without_timestamp_waits() -> None:
    # Open, a positive delay, but we have no record of when it opened -> wait.
    assert window_suppresses(True, opened_at=None, now=100.0, delay_seconds=60.0) is (
        False
    )
