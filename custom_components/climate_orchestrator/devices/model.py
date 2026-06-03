"""Value objects for device control (pure, no Home Assistant dependencies).

``Mode`` values intentionally mirror Home Assistant's ``HVACMode`` strings so a
command maps straight onto a ``climate.set_hvac_mode`` service call, while this
module stays import-free of Home Assistant for easy testing.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Mode(StrEnum):
    """HVAC modes we command (subset of HA's HVACMode, same string values)."""

    OFF = "off"
    HEAT = "heat"
    COOL = "cool"
    DRY = "dry"


@dataclass(frozen=True, slots=True)
class AdapterCapabilities:
    """What a managed device can do, derived from its reported attributes."""

    can_heat: bool
    can_cool: bool
    can_dry: bool
    min_temp: float
    max_temp: float
    target_step: float


@dataclass(frozen=True, slots=True)
class DeviceState:
    """A device's currently reported state."""

    available: bool
    hvac_mode: str | None
    current_temp: float | None
    target_temp: float | None


@dataclass(frozen=True, slots=True)
class DeviceCommand:
    """The desired state for a device this cycle."""

    hvac_mode: Mode
    target_temp: float | None


@dataclass(frozen=True, slots=True)
class Writes:
    """The minimal set of service calls needed to reach a command."""

    set_hvac_mode: Mode | None = None
    set_temperature: float | None = None

    @property
    def is_empty(self) -> bool:
        """Whether nothing needs to be written (a no-op)."""
        return self.set_hvac_mode is None and self.set_temperature is None
