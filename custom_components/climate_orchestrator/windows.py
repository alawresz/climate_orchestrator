"""Debounced window-open tracking with grace-delay rechecks.

``WindowMonitor`` owns the per-area "window first opened at" timers behind
the window-open guard: an open window suppresses a device only after staying
open for the configured grace delay, and a one-shot recheck re-runs control
exactly when that delay elapses instead of waiting for the next keepalive.
The pure suppression predicate lives in ``control.window``; this module is
the stateful, HA-side bookkeeping around it.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from homeassistant.core import callback
from homeassistant.helpers.event import async_call_later

from .control.window import window_suppresses

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from homeassistant.core import CALLBACK_TYPE, HomeAssistant

    from .models import DeviceReading


class WindowMonitor:
    """Per-area window-open debounce plus the grace-delay recheck timer."""

    def __init__(
        self, hass: HomeAssistant, request_recheck: Callable[[], None]
    ) -> None:
        """Bind to hass and the coordinator's recheck trigger."""
        self._hass = hass
        self._request_recheck = request_recheck
        self._open_since: dict[str, float] = {}
        self._recheck_unsub: CALLBACK_TYPE | None = None
        self._recheck_at: float | None = None  # monotonic deadline

    @callback
    def suppresses(self, reading: DeviceReading, delay_seconds: float) -> bool:
        """Debounced window-open for a device: open only after the grace delay.

        Tracks when each area's window first opened and suppresses heating/
        cooling once it has stayed open for ``delay_seconds``. Schedules a
        one-shot refresh so control re-runs exactly when the delay elapses
        (rather than waiting for the next keepalive).
        """
        raw_open = reading.window_open
        area_id = reading.area_id
        if not raw_open:
            if area_id is not None:
                self._open_since.pop(area_id, None)
            return False
        if area_id is None:
            # No area key to debounce against; honour the delay only as on/off.
            return delay_seconds <= 0.0

        now = time.monotonic()
        opened_at = self._open_since.get(area_id)
        if opened_at is None:
            self._open_since[area_id] = opened_at = now
            if delay_seconds > 0.0:
                self._schedule_recheck(delay_seconds)
        elif (
            self._recheck_unsub is None
            and (remaining := delay_seconds - (now - opened_at)) > 0.0
        ):
            # Re-arm: a window still inside its grace period but with no timer
            # pending (e.g. an earlier-deadline window fired and was gone by
            # then) would otherwise only be caught by the next keepalive.
            self._schedule_recheck(remaining)
        return window_suppresses(raw_open, opened_at, now, delay_seconds)

    @callback
    def _schedule_recheck(self, delay_seconds: float) -> None:
        """Re-run control shortly after a window's grace delay expires.

        One timer, earliest deadline wins: a window opening later must not
        postpone an earlier window's recheck (the keepalive would still catch
        it, but up to a minute late). The recheck refresh re-evaluates every
        area, so the earliest deadline serves all pending windows.
        """
        now = time.monotonic()
        deadline = now + delay_seconds
        if self._recheck_unsub is not None:
            pending = self._recheck_at
            if pending is not None and pending <= deadline:
                return  # an earlier (or equal) recheck is already pending
            self._recheck_unsub()
        self._recheck_at = deadline

        @callback
        def _fire(_now: object) -> None:
            self._recheck_unsub = None
            self._recheck_at = None
            self._request_recheck()

        # A small margin ensures the elapsed check passes when it fires.
        self._recheck_unsub = async_call_later(self._hass, delay_seconds + 0.5, _fire)

    @callback
    def prune(self, live_areas: Iterable[str]) -> None:
        """Evict timers for areas no longer backing any managed device.

        A registry area change doesn't reload the entry, so without this the
        dict would keep dead area keys for the coordinator's lifetime.
        """
        live = set(live_areas)
        for area_id in list(self._open_since):
            if area_id not in live:
                del self._open_since[area_id]

    @callback
    def shutdown(self) -> None:
        """Cancel the pending recheck timer (entry unload/reload).

        Unload-safe: cancelled handles never fire, and if the timer lands
        mid-unload the recheck goes through an entry-tracked background task
        that HA cancels with the entry.
        """
        if self._recheck_unsub is not None:
            self._recheck_unsub()
            self._recheck_unsub = None
            self._recheck_at = None
