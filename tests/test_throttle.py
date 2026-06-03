"""Tests for the pure setpoint-write throttle."""

from __future__ import annotations

from custom_components.climate_orchestrator.control.throttle import throttle_setpoint

_KW = {"min_change": 0.5, "min_interval_s": 180.0, "keepalive_s": 900.0}


def test_first_write_is_always_sent() -> None:
    """With no previous value, the new setpoint is written immediately."""
    assert throttle_setpoint(None, None, 22.0, 100.0, **_KW) == (22.0, 100.0)


def test_small_change_is_held() -> None:
    """A sub-threshold change is held (returns the previous value/timestamp)."""
    # 0.4 < 0.5, even after the interval.
    assert throttle_setpoint(22.0, 100.0, 22.4, 400.0, **_KW) == (22.0, 100.0)


def test_meaningful_change_too_soon_is_held() -> None:
    """A big change within the min interval is still held."""
    # change 3.0 >= 0.5 but elapsed 60 < 180.
    assert throttle_setpoint(22.0, 100.0, 25.0, 160.0, **_KW) == (22.0, 100.0)


def test_meaningful_change_after_interval_is_written() -> None:
    """A big-enough change after the interval is written with the new time."""
    assert throttle_setpoint(22.0, 100.0, 23.0, 300.0, **_KW) == (23.0, 300.0)


def test_keepalive_forces_a_reassert() -> None:
    """Past the keep-alive, even an unchanged value is re-asserted (new ts)."""
    assert throttle_setpoint(22.0, 100.0, 22.0, 1001.0, **_KW) == (22.0, 1001.0)
