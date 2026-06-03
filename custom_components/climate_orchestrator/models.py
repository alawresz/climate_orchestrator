"""Immutable value objects for the Climate Orchestrator integration."""

from __future__ import annotations

from dataclasses import dataclass


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

    @property
    def degraded(self) -> bool:
        """Whether at least one managed device is currently unavailable."""
        return bool(self.unavailable_devices)

    @property
    def any_window_open(self) -> bool:
        """Whether any managed area currently reports a window/door open."""
        return any(r.window_open for r in self.readings.values())


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
