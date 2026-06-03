"""Immutable value objects for the Climate Orchestrator integration."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Status(StrEnum):
    """Operational status of the orchestrator as a whole.

    ``INITIALIZING`` covers the warm-up window right after a restart, before
    any managed device has reported a usable temperature — transient gaps that
    would otherwise raise alarming repairs are held back until we leave it.
    """

    INITIALIZING = "initializing"
    OK = "ok"
    DEGRADED = "degraded"


@dataclass(frozen=True, slots=True)
class DeviceReading:
    """A snapshot of one managed device and its resolved area sensors."""

    entity_id: str
    available: bool
    area_id: str | None
    area_temperature_sensor: str | None
    area_humidity_sensor: str | None
    area_temperature: float | None
    area_humidity: float | None
    window_open: bool = False


@dataclass(frozen=True, slots=True)
class SmartClimateData:
    """The coordinator's per-cycle snapshot shared with all entities."""

    home_avg_temperature: float | None
    home_avg_humidity: float | None
    available_devices: frozenset[str]
    unavailable_devices: frozenset[str]
    readings: dict[str, DeviceReading]
    tracked_entities: frozenset[str]
    stale_sensors: frozenset[str] = frozenset()
    status: Status = Status.OK

    @property
    def initializing(self) -> bool:
        """Whether the orchestrator is still in its post-restart warm-up."""
        return self.status is Status.INITIALIZING

    @property
    def degraded(self) -> bool:
        """Whether a managed device is unavailable *after* warm-up.

        Suppressed while ``INITIALIZING`` so a restart doesn't briefly flash a
        degraded state before sensors and devices have reported in.
        """
        return self.status is Status.DEGRADED

    @property
    def any_window_open(self) -> bool:
        """Whether any managed area currently reports a window/door open."""
        return any(r.window_open for r in self.readings.values())


@dataclass(frozen=True, slots=True)
class AcSetpoint:
    """The last AC cooling setpoint written, and when (monotonic seconds).

    Feeds the write throttle: a new cooling command may have its setpoint
    replaced with ``value`` until enough time or temperature delta has passed.
    """

    value: float
    written_at: float


@dataclass(frozen=True, slots=True)
class RuntimeSample:
    """One (monotonic time, was-running) sample for the cycle/runtime counters."""

    at: float
    running: bool


@dataclass(frozen=True, slots=True)
class Band:
    """A comfort band: heat below ``heat_edge``, cool above ``cool_edge``."""

    heat_edge: float
    cool_edge: float

    @property
    def target(self) -> float:
        """The neutral midpoint (used only as a safety cap for the targets)."""
        return (self.heat_edge + self.cool_edge) / 2

    def heat_target(self, tolerance: float) -> float:
        """Heating control target: just above the heat edge (trigger + tolerance).

        Capped at the midpoint so it can never cross the cooling target, even
        for a band narrower than twice the tolerance.
        """
        return min(self.heat_edge + tolerance, self.target)

    def cool_target(self, tolerance: float) -> float:
        """Cooling control target: just below the cool edge (trigger - tolerance).

        Floored at the midpoint for the same anti-crossover reason.
        """
        return max(self.cool_edge - tolerance, self.target)
