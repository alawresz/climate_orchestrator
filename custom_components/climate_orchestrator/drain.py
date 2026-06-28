"""Debounced AC-drain tracking with a grace-delay recheck.

``DrainMonitor`` owns the single "drain sensor first went active at" timer
behind the AC drain guard: a full condensate tank holds the AC off only after
the sensor has stayed active for the configured grace window, and a one-shot
recheck re-runs control exactly when that delay elapses instead of waiting for
the next keepalive. The whole-home guard is a single global sensor, so unlike
``WindowMonitor`` there is no per-area bookkeeping — just one deadline.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from homeassistant.core import callback
from homeassistant.helpers.event import async_call_later

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import CALLBACK_TYPE, HomeAssistant


class DrainMonitor:
    """Drain-sensor debounce plus the grace-delay recheck timer."""

    def __init__(
        self, hass: HomeAssistant, request_recheck: Callable[[], None]
    ) -> None:
        """Bind to hass and the coordinator's recheck trigger."""
        self._hass = hass
        self._request_recheck = request_recheck
        self._active_since: float | None = None
        self._recheck_unsub: CALLBACK_TYPE | None = None

    @callback
    def blocks(self, active: bool, grace_seconds: float) -> bool:
        """Whether the AC should be held off: active beyond the grace window.

        Tracks when the drain sensor first went active and reports a block once
        it has stayed active for ``grace_seconds``. Schedules a one-shot refresh
        so control re-runs exactly when the grace elapses (rather than waiting
        for the next keepalive). Going inactive resets the timer immediately, so
        cooling resumes as soon as the tank is emptied.
        """
        if not active:
            self._active_since = None
            self._cancel()
            return False

        now = time.monotonic()
        if self._active_since is None:
            self._active_since = now
        elapsed = now - self._active_since
        if elapsed >= grace_seconds:
            return True
        if self._recheck_unsub is None:
            self._schedule_recheck(grace_seconds - elapsed)
        return False

    @callback
    def _schedule_recheck(self, delay_seconds: float) -> None:
        """Re-run control shortly after the grace delay expires."""

        @callback
        def _fire(_now: object) -> None:
            self._recheck_unsub = None
            self._request_recheck()

        # A small margin ensures the elapsed check passes when it fires.
        self._recheck_unsub = async_call_later(self._hass, delay_seconds + 0.5, _fire)

    @callback
    def _cancel(self) -> None:
        """Drop any pending recheck timer."""
        if self._recheck_unsub is not None:
            self._recheck_unsub()
            self._recheck_unsub = None

    @callback
    def shutdown(self) -> None:
        """Cancel the pending recheck timer (entry unload/reload)."""
        self._cancel()
