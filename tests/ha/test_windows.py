"""Behavioral tests for the WindowMonitor's grace-delay recheck timer.

These drive the monitor directly (its API is the coordinator-facing surface)
so the timer mechanics — firing, earliest-deadline arbitration, re-arming —
can be asserted without a full control cycle around them.
"""

from __future__ import annotations

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.climate_orchestrator.models import DeviceReading
from custom_components.climate_orchestrator.windows import WindowMonitor


def _reading(area_id: str | None, *, window_open: bool = True) -> DeviceReading:
    """A minimal device reading carrying only what the monitor looks at."""
    return DeviceReading(
        entity_id="climate.trv_1",
        available=True,
        area_id=area_id,
        area_temperature_sensor=None,
        area_humidity_sensor=None,
        area_temperature=None,
        area_humidity=None,
        window_open=window_open,
    )


async def test_recheck_timer_fires_when_the_grace_delay_elapses(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """The one-shot timer requests a control re-run exactly after the delay.

    Without it, a window opened mid-cycle would only be caught by the next
    keepalive — up to a minute after the grace period actually ended.
    """
    rechecks: list[bool] = []
    monitor = WindowMonitor(hass, lambda: rechecks.append(True))

    # Freshly opened: inside the grace period, not suppressed, timer armed.
    assert monitor.suppresses(_reading("living"), 600.0) is False
    assert not rechecks

    freezer.tick(timedelta(seconds=601))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert rechecks  # control was re-run by the timer, not a keepalive
    assert monitor.suppresses(_reading("living"), 600.0) is True


async def test_window_without_an_area_honours_the_delay_as_on_off(
    hass: HomeAssistant,
) -> None:
    """No area key means no debounce timestamp: any delay disables suppression."""
    monitor = WindowMonitor(hass, lambda: None)
    assert monitor.suppresses(_reading(None), 600.0) is False
    assert monitor.suppresses(_reading(None), 0.0) is True


async def test_later_window_does_not_postpone_an_earlier_recheck(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """One timer, earliest deadline wins; the survivor re-arms for the rest."""
    rechecks: list[bool] = []
    monitor = WindowMonitor(hass, lambda: rechecks.append(True))

    monitor.suppresses(_reading("living"), 600.0)  # deadline t+600
    freezer.tick(timedelta(seconds=300))
    monitor.suppresses(_reading("bedroom"), 600.0)  # t+900: must NOT replace t+600

    freezer.tick(timedelta(seconds=301))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert len(rechecks) == 1  # fired at the living room's deadline

    # The living room is now past its grace period; the bedroom is still
    # inside it and — with the timer consumed — re-arms for its remainder.
    assert monitor.suppresses(_reading("living"), 600.0) is True
    assert monitor.suppresses(_reading("bedroom"), 600.0) is False

    freezer.tick(timedelta(seconds=301))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert len(rechecks) == 2
    assert monitor.suppresses(_reading("bedroom"), 600.0) is True


async def test_earlier_deadline_replaces_a_later_pending_recheck(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """A window due sooner cancels and replaces a later pending timer.

    Happens when the user shortens the delay between two windows opening:
    the second window's (shorter) deadline lands before the first one's.
    """
    rechecks: list[bool] = []
    monitor = WindowMonitor(hass, lambda: rechecks.append(True))

    monitor.suppresses(_reading("living"), 600.0)  # pending at t+600
    freezer.tick(timedelta(seconds=60))
    monitor.suppresses(_reading("bedroom"), 120.0)  # due at t+180: replaces it

    freezer.tick(timedelta(seconds=121))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert len(rechecks) == 1  # fired at the bedroom's earlier deadline
    assert monitor.suppresses(_reading("bedroom"), 120.0) is True
    # The living room window is still mid-grace; this re-arms a timer, so
    # shut the monitor down the way entry unload would.
    assert monitor.suppresses(_reading("living"), 600.0) is False
    monitor.shutdown()
