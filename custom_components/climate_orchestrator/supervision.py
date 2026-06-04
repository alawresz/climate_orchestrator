"""Per-device supervision: the command-ignored watchdog and manual takeover.

``DeviceSupervisor`` watches the two ways a device's state can legitimately
diverge from what the coordinator commanded and tells them apart by
trajectory:

* never reached the command → **watchdog** (child lock, weak radio, dying
  battery, a wedged integration): a repair after ``COMMAND_IGNORED_SECONDS``;
* was at the command and then moved away with no write from us → **manual
  override** (a human, or their automation): stand back from that device for
  the configured duration instead of silently fighting the change.

Both latch their state on the device's ``DeviceRuntime`` and announce edges
through the :class:`~.events.EventBridge`.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import callback

from .const import (
    COMMAND_IGNORED_SECONDS,
    EVENT_TYPE_IGNORING_ENDED,
    EVENT_TYPE_IGNORING_STARTED,
    EVENT_TYPE_OVERRIDE_ENDED,
    EVENT_TYPE_OVERRIDE_STARTED,
    TARGET_TEMP_STEP,
)
from .devices.model import Mode
from .repairs import command_ignored_issue
from .settings import clamped_number_value
from .util import as_float

if TYPE_CHECKING:
    from collections.abc import Iterable

    from homeassistant.core import Event, EventStateChangedData, HomeAssistant, State

    from .control.engine import DeviceDecision
    from .coordinator import DeviceRuntime
    from .events import EventBridge

_LOGGER = logging.getLogger(__name__)


class DeviceSupervisor:
    """Watchdog + manual-override takeover for one config entry's devices."""

    def __init__(self, hass: HomeAssistant, entry_id: str, events: EventBridge) -> None:
        """Bind to the entry and the event bridge edges are announced on."""
        self._hass = hass
        self._entry_id = entry_id
        self._events = events

    # --- Command-ignored watchdog ---------------------------------------------

    @callback
    def watch_compliance(
        self, entity_id: str, runtime: DeviceRuntime, mode: str | None, desired: str
    ) -> None:
        """Watchdog: flag a device whose service calls succeed but do nothing.

        A child lock, a weak radio link, a dying battery, or a wedged upstream
        integration all look the same from here: ``set_hvac_mode`` returns
        fine, yet the entity's state never becomes the commanded mode. When
        one *unchanged* commanded mode stays unreflected past
        ``COMMAND_IGNORED_SECONDS``, raise a per-device repair; it clears the
        moment the device converges. Loud failures are excluded — those are
        the control-failure repair's job.
        """
        if mode == desired or runtime.command_failing:
            self.reset_watchdog(entity_id, runtime)
            return
        now = time.monotonic()
        if runtime.ignored_mode != desired or runtime.ignored_since is None:
            runtime.ignored_mode = desired
            runtime.ignored_since = now
        active = now - runtime.ignored_since >= COMMAND_IGNORED_SECONDS
        command_ignored_issue(self._hass, entity_id, active=active)
        self._set_ignoring(entity_id, runtime, active=active, mode=desired)

    @callback
    def reset_watchdog(self, entity_id: str, runtime: DeviceRuntime) -> None:
        """Drop any non-compliance streak (converged, overridden, offline)."""
        runtime.ignored_mode = None
        runtime.ignored_since = None
        command_ignored_issue(self._hass, entity_id, active=False)
        self._set_ignoring(entity_id, runtime, active=False)

    @callback
    def _set_ignoring(
        self,
        entity_id: str,
        runtime: DeviceRuntime,
        *,
        active: bool,
        mode: str | None = None,
    ) -> None:
        """Latch the watchdog verdict and fire a bus event on each edge."""
        if active == runtime.ignoring:
            return
        runtime.ignoring = active
        if active:
            self._events.fire(
                EVENT_TYPE_IGNORING_STARTED,
                {"entity_id": entity_id, "commanded_mode": mode},
            )
        else:
            self._events.fire(EVENT_TYPE_IGNORING_ENDED, {"entity_id": entity_id})

    # --- Manual-override takeover -----------------------------------------------

    @callback
    def detect_override(
        self,
        event: Event[EventStateChangedData],
        devices: dict[str, DeviceRuntime],
        device_ids: Iterable[str],
    ) -> None:
        """Spot a human (or external automation) adjusting a managed device.

        Our own writes echo back *matching* the active command, and a device
        that never reached the command is the watchdog's case — the takeover
        signature is a device that **was** at the commanded state and then
        moved away (in mode, or in target setpoint by at least one device
        step) with no new command from us.
        """
        entity_id = event.data["entity_id"]
        if entity_id not in device_ids:
            return  # an area sensor, not a managed device
        runtime = devices.get(entity_id)
        if runtime is None or (command := runtime.command) is None:
            return
        duration_min = clamped_number_value(
            self._hass, self._entry_id, "manual_override_duration"
        )
        if duration_min <= 0.0:
            return  # takeover disabled
        old = event.data["old_state"]
        new = event.data["new_state"]
        if (
            old is None
            or new is None
            or old.state in (STATE_UNAVAILABLE, STATE_UNKNOWN)
            or new.state in (STATE_UNAVAILABLE, STATE_UNKNOWN)
        ):
            return  # (un)availability churn is never a human

        step = as_float(new.attributes.get("target_temp_step")) or TARGET_TEMP_STEP

        def _matches(state: State) -> bool:
            if state.state != command.hvac_mode.value:
                return False
            if command.target_temp is None or command.hvac_mode is Mode.OFF:
                return True
            target = as_float(state.attributes.get("temperature"))
            return target is None or abs(target - command.target_temp) < step

        if _matches(old) and not _matches(new):
            self._start_override(entity_id, runtime, duration_min)

    @callback
    def _start_override(
        self, entity_id: str, runtime: DeviceRuntime, duration_min: float
    ) -> None:
        """Stop driving a device the user just adjusted, for the set duration."""
        runtime.override_until = time.monotonic() + duration_min * 60.0
        # The device will now intentionally diverge from our last command —
        # that must not look like non-compliance when the override ends.
        self.reset_watchdog(entity_id, runtime)
        _LOGGER.info(
            "climate_orchestrator: manual change detected on %s; "
            "standing back for %.0f min",
            entity_id,
            duration_min,
        )
        self._events.fire(
            EVENT_TYPE_OVERRIDE_STARTED,
            {"entity_id": entity_id, "duration_minutes": duration_min},
        )

    @callback
    def end_override(self, entity_id: str, runtime: DeviceRuntime, reason: str) -> None:
        """Resume driving a device (next cycle reconciles it to the band)."""
        runtime.override_until = None
        self._events.fire(
            EVENT_TYPE_OVERRIDE_ENDED, {"entity_id": entity_id, "reason": reason}
        )

    @callback
    def clear_overrides(self, devices: dict[str, DeviceRuntime], reason: str) -> None:
        """End every active override (the user reasserted whole-home intent)."""
        for entity_id, runtime in devices.items():
            if runtime.override_until is not None:
                self.end_override(entity_id, runtime, reason)

    @callback
    def override_active(
        self, entity_id: str, runtime: DeviceRuntime, decision: DeviceDecision
    ) -> bool:
        """Whether the device's override still holds this cycle.

        Expiry is checked here (per cycle, so within a keepalive of the
        deadline) and frost protection punches through unconditionally —
        safety beats courtesy.
        """
        if runtime.override_until is None:
            return False
        if decision.reason == "frost_protection":
            self.end_override(entity_id, runtime, "frost_protection")
            return False
        if time.monotonic() >= runtime.override_until:
            self.end_override(entity_id, runtime, "expired")
            return False
        return True

    @callback
    def handle_unavailable(self, entity_id: str, runtime: DeviceRuntime) -> None:
        """Reset supervision for an offline device.

        An offline device can't comply with anything (so a watchdog streak
        would be misreported unavailability) and a manual override on a
        device that vanished is moot.
        """
        self.reset_watchdog(entity_id, runtime)
        if runtime.override_until is not None:
            self.end_override(entity_id, runtime, "unavailable")
