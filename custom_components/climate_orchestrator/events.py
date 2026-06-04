"""Bus events and self-clearing bell notifications.

``EventBridge`` owns the edge-detection state and announces operational
transitions as ``climate_orchestrator_event`` bus events (one event type,
discriminated by a ``type`` field — the zha_event pattern). Everything is
edge-triggered against the previous cycle, never fired once per cycle, so the
events are safe to notify on directly. The two interrupt-worthy conditions
(frost protection, degraded status) additionally raise a persistent
notification in HA's notification panel, created on the rising edge and
dismissed by itself when the condition clears.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components import persistent_notification as pn
from homeassistant.core import callback

from .const import (
    DOMAIN,
    EVENT_CLIMATE_ORCHESTRATOR,
    EVENT_TYPE_DEHUMIDIFYING_ENDED,
    EVENT_TYPE_DEHUMIDIFYING_STARTED,
    EVENT_TYPE_FROST_ENDED,
    EVENT_TYPE_FROST_STARTED,
    EVENT_TYPE_STATUS_CHANGED,
    EVENT_TYPE_WINDOW_PAUSE_ENDED,
    EVENT_TYPE_WINDOW_PAUSE_STARTED,
)
from .models import Status

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .control.engine import DeviceDecision
    from .models import SmartClimateData
    from .settings import RuntimeSettings


class EventBridge:
    """Edge-triggered bus events + bell notifications for one config entry."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Bind to the entry; edge state starts empty (quiet first cycle)."""
        self._hass = hass
        self._entry_id = entry_id
        # Last cycle's home-wide flags, the devices whose heating/cooling was
        # window-paused, and the status — diffed each cycle for the edges.
        self._flags: dict[str, bool] = {}
        self._window_paused: frozenset[str] = frozenset()
        self._last_status: Status | None = None

    @callback
    def fire(self, event_type: str, data: dict[str, Any]) -> None:
        """Fire one bus event (single event type, discriminated by ``type``)."""
        self._hass.bus.async_fire(
            EVENT_CLIMATE_ORCHESTRATOR, {"type": event_type, **data}
        )

    @callback
    def _sync_notification(
        self, key: str, *, rising: bool, clear: bool, title: str, message: str
    ) -> None:
        """Keep one self-clearing bell notification in step with its condition.

        Created only on the rising edge (so a manually dismissed notice stays
        dismissed while the condition persists) and dismissed whenever the
        condition is gone — dismissing an absent id is a no-op.
        """
        notification_id = f"{DOMAIN}_{self._entry_id}_{key}"
        if clear:
            pn.async_dismiss(self._hass, notification_id)
        elif rising:
            pn.async_create(
                self._hass, message, title=title, notification_id=notification_id
            )

    @callback
    def dispatch_cycle(
        self,
        data: SmartClimateData,
        window_state: dict[str, bool],
        settings: RuntimeSettings,
        decisions: dict[str, DeviceDecision],
    ) -> None:
        """Fire bus events (and sync notifications) on operational transitions.

        The frost/dew predicates are computed from the same decisions that
        drive the binary sensors, so events can never disagree with what the
        dashboard shows. Watchdog, manual-override, and boost transitions are
        fired at their own edges (the supervisor, the climate entity), not
        here.
        """
        frost = any(d.reason == "frost_protection" for d in decisions.values())
        if frost != self._flags.get("frost", False):
            frosty = sorted(
                key for key, d in decisions.items() if d.reason == "frost_protection"
            )
            self.fire(
                EVENT_TYPE_FROST_STARTED if frost else EVENT_TYPE_FROST_ENDED,
                {"entities": frosty},
            )
            self._sync_notification(
                "frost_protection",
                rising=frost and settings.event_notifications,
                clear=not frost,
                title="Climate Orchestrator: frost protection",
                message=(
                    "A room is at or below the frost-protection temperature; "
                    "forced heating is engaged for: " + ", ".join(frosty)
                ),
            )

        dew = any(d.dry_mode for d in decisions.values())
        if dew != self._flags.get("dew", False):
            drying = sorted(key for key, d in decisions.items() if d.dry_mode)
            self.fire(
                EVENT_TYPE_DEHUMIDIFYING_STARTED
                if dew
                else EVENT_TYPE_DEHUMIDIFYING_ENDED,
                {"entities": drying},
            )
        self._flags = {"frost": frost, "dew": dew}

        paused = frozenset(eid for eid, blocked in window_state.items() if blocked)
        for started, entities in (
            (True, paused - self._window_paused),
            (False, self._window_paused - paused),
        ):
            for entity_id in sorted(entities):
                reading = data.readings.get(entity_id)
                self.fire(
                    EVENT_TYPE_WINDOW_PAUSE_STARTED
                    if started
                    else EVENT_TYPE_WINDOW_PAUSE_ENDED,
                    {
                        "entity_id": entity_id,
                        "area_id": reading.area_id if reading else None,
                    },
                )
        self._window_paused = paused

        status = data.status
        # _last_status is None on the first cycle after setup: report only
        # *changes*, not the initial state, so restarts stay quiet.
        if self._last_status is not None and status is not self._last_status:
            self.fire(
                EVENT_TYPE_STATUS_CHANGED,
                {
                    "from": self._last_status.value,
                    "to": status.value,
                    "unavailable_devices": sorted(data.unavailable_devices),
                },
            )
            self._sync_notification(
                "degraded",
                rising=(status is Status.DEGRADED) and settings.event_notifications,
                clear=status is not Status.DEGRADED,
                title="Climate Orchestrator: degraded",
                message=(
                    "Some managed devices or sensors are not usable: "
                    + (
                        ", ".join(sorted(data.unavailable_devices))
                        or "no temperature source"
                    )
                ),
            )
        self._last_status = status
