"""Translate an engine decision into a concrete device command (pure).

Heaters (TRVs) heat toward the band target. Coolers (ACs) cool toward a target
biased *below* the real target so the AC's own sensor doesn't satisfy before the
room does (DESIGN.md §6.2); an idle AC under the dew-point guard runs dry mode.
"""

from __future__ import annotations

from ..const import AC_COOL_KICK
from ..control.engine import DeviceDecision, DeviceKind
from ..control.hysteresis import Demand
from ..models import Band
from .model import AdapterCapabilities, DeviceCommand, Mode


def _clamp(value: float, caps: AdapterCapabilities) -> float:
    """Snap to the device's step and clamp to its allowed range."""
    stepped = round(value / caps.target_step) * caps.target_step
    return max(caps.min_temp, min(caps.max_temp, stepped))


def build_command(
    decision: DeviceDecision,
    kind: DeviceKind,
    *,
    band: Band,
    ac_setpoint_bias: float,
    caps: AdapterCapabilities,
    tolerance: float = 0.0,
    device_current_temp: float | None = None,
    room_temp: float | None = None,
) -> DeviceCommand:
    """Build the device command for a decision.

    The commanded setpoint is the directional control target (``edge ±
    tolerance``), clamped to the device's accepted range and snapped to its
    step — so a large bias can never push the AC below its own minimum.

    For cooling, the setpoint is *also* anchored to the AC's own reported
    temperature, because an AC only runs its compressor when the setpoint is
    below what its internal sensor reads — otherwise it just idles or fans. The
    anchor is **proportional to how far the room is above target**: the setpoint
    is pushed `max(room_above_target, AC_COOL_KICK)` below the AC's reading, so a
    room 3° over target drives the AC ~3° below its sensor (not a fixed 1°). The
    room sensor still ends the call (the engine releases the demand → off).
    """
    if kind is DeviceKind.HEATER:
        if decision.demand is Demand.HEAT and caps.can_heat:
            return DeviceCommand(Mode.HEAT, _clamp(band.heat_target(tolerance), caps))
        return DeviceCommand(Mode.OFF, None)

    # Cooler (AC).
    if decision.demand is Demand.COOL and caps.can_cool:
        cool_target = band.cool_target(tolerance)
        target = cool_target - ac_setpoint_bias
        if device_current_temp is not None:
            room_above = max(0.0, room_temp - cool_target) if room_temp else 0.0
            drive = max(room_above, AC_COOL_KICK)
            target = min(target, device_current_temp - drive)
        return DeviceCommand(Mode.COOL, _clamp(target, caps))
    # Heating assist: the engine only yields HEAT for a cooler when assist is on.
    # Drive to the heat target like a TRV; the room sensor ends the call.
    if decision.demand is Demand.HEAT and caps.can_heat:
        return DeviceCommand(Mode.HEAT, _clamp(band.heat_target(tolerance), caps))
    if decision.dry_mode and caps.can_dry:
        return DeviceCommand(Mode.DRY, None)
    return DeviceCommand(Mode.OFF, None)
