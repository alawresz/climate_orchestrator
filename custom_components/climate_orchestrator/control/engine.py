"""Arbitration engine: turn readings + settings into a per-device decision.

Pure logic (no Home Assistant). For each managed device it applies, in priority
order: master-off, availability, frost protection, window-open, the hysteresis
demand, device-capability gating, outdoor-temp gating, and finally the AC
dew-point dry-mode guard (see DESIGN.md §5.4, §5.5, §6.2).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from ..const import MAX_TEMP, MIN_TEMP
from .comfort import dew_point, effective_temperature
from .hysteresis import Demand, evaluate_demand
from .numeric import clamp

if TYPE_CHECKING:
    from ..models import Band


class DeviceKind(StrEnum):
    """A device either heats (TRV) or cools (AC)."""

    HEATER = "heater"
    COOLER = "cooler"


@dataclass(frozen=True, slots=True)
class GlobalInput:
    """Whole-home settings and aggregates shared across devices this cycle."""

    band: Band
    release_offset: float
    tolerance: float = 0.0
    home_temp: float | None = None
    home_humidity: float | None = None
    outdoor_temp: float | None = None
    master_off: bool = False
    use_comfort: bool = True
    comfort_influence: float = 1.0
    dew_point_threshold: float | None = None
    frost_temp: float | None = None
    heat_off_outdoor: float | None = None
    cool_off_outdoor: float | None = None
    window_detection: bool = True
    ac_ignore_window: bool = False
    frost_protection: bool = True
    outdoor_gating: bool = True
    ac_heating_assist: bool = False


@dataclass(frozen=True, slots=True)
class DeviceInput:
    """One managed device's per-cycle inputs."""

    key: str
    kind: DeviceKind
    available: bool
    local_temp: float | None
    local_humidity: float | None = None
    window_open: bool = False
    other_window_open: bool = False
    previous: Demand = Demand.IDLE
    # Per-area comfort band offset (°C); positive runs the room warmer.
    offset: float = 0.0


@dataclass(frozen=True, slots=True)
class DeviceDecision:
    """The engine's decision for one device."""

    key: str
    demand: Demand
    dry_mode: bool
    reason: str


def _decision(device: DeviceInput, demand: Demand, reason: str) -> DeviceDecision:
    return DeviceDecision(key=device.key, demand=demand, dry_mode=False, reason=reason)


def decide(device: DeviceInput, g: GlobalInput) -> DeviceDecision:
    """Decide what a single device should do this cycle."""
    if g.master_off:
        return _decision(device, Demand.IDLE, "master_off")
    if not device.available:
        return _decision(device, Demand.IDLE, "unavailable")

    # Frost protection (dry-bulb, heaters only) overrides everything else.
    raw_local = device.local_temp if device.local_temp is not None else g.home_temp
    if (
        g.frost_protection
        and g.frost_temp is not None
        and device.kind is DeviceKind.HEATER
        and raw_local is not None
        and raw_local < g.frost_temp
    ):
        return _decision(device, Demand.HEAT, "frost_protection")

    # A portable/exhaust-hose AC needs its own window open to vent, so a cooler
    # can ignore *its own area's* window — but it still stops if a window is open
    # in another room (cooling the home would be wasteful). Heaters always stop.
    window_blocks = device.window_open
    if device.kind is DeviceKind.COOLER and g.ac_ignore_window:
        window_blocks = device.other_window_open
    if g.window_detection and window_blocks:
        return _decision(device, Demand.IDLE, "window_open")

    # Comfort-adjusted readings, with cross-fallback between local and home.
    # The per-area offset biases only the *local* reading (not the home
    # average): a positive offset subtracts from the room's perceived
    # temperature, so it engages sooner and releases later — i.e. runs warmer.
    # Clamped so the shifted reading can't escape the usable temperature range.
    local_eff = (
        clamp(
            effective_temperature(
                device.local_temp,
                device.local_humidity,
                use_comfort=g.use_comfort,
                influence=g.comfort_influence,
            )
            - device.offset,
            MIN_TEMP,
            MAX_TEMP,
        )
        if device.local_temp is not None
        else None
    )
    home_eff = (
        effective_temperature(
            g.home_temp,
            g.home_humidity,
            use_comfort=g.use_comfort,
            influence=g.comfort_influence,
        )
        if g.home_temp is not None
        else None
    )
    local_for = local_eff if local_eff is not None else home_eff
    home_for = home_eff if home_eff is not None else local_eff
    if local_for is None or home_for is None:
        return _decision(device, Demand.IDLE, "no_data")

    demand = evaluate_demand(
        local=local_for,
        home=home_for,
        band=g.band,
        release_offset=g.release_offset,
        previous=device.previous,
        tolerance=g.tolerance,
    )

    # Capability gating: heaters can't cool; ACs only heat with assist enabled.
    if demand is Demand.COOL and device.kind is DeviceKind.HEATER:
        demand = Demand.IDLE
    if (
        demand is Demand.HEAT
        and device.kind is DeviceKind.COOLER
        and not g.ac_heating_assist
    ):
        demand = Demand.IDLE

    # Outdoor-temp gating.
    outdoor_gated = False
    if (
        g.outdoor_gating
        and g.outdoor_temp is not None
        and (
            (
                demand is Demand.HEAT
                and g.heat_off_outdoor is not None
                and g.outdoor_temp >= g.heat_off_outdoor
            )
            or (
                demand is Demand.COOL
                and g.cool_off_outdoor is not None
                and g.outdoor_temp <= g.cool_off_outdoor
            )
        )
    ):
        demand = Demand.IDLE
        outdoor_gated = True

    # Dew-point guard: an idle AC may run dry mode to dehumidify; an actively
    # cooling AC already dehumidifies, so it takes priority.
    if (
        device.kind is DeviceKind.COOLER
        and demand is not Demand.COOL
        and g.dew_point_threshold is not None
        and device.local_temp is not None
        and device.local_humidity is not None
        and dew_point(device.local_temp, device.local_humidity) > g.dew_point_threshold
    ):
        return DeviceDecision(
            key=device.key, demand=demand, dry_mode=True, reason="dew_point_guard"
        )

    reason = "outdoor_gating" if outdoor_gated else demand.value
    return DeviceDecision(key=device.key, demand=demand, dry_mode=False, reason=reason)
